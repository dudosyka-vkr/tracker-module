"""Application shell with QStackedWidget navigation."""

from __future__ import annotations

import platform
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMainWindow, QMessageBox, QStackedWidget

from eyetracker.core.fixation_offline import detect_fixations_ivt
from eyetracker.core.gaze_points_map import _compute_velocities
from eyetracker.core.monitor import resolve_screen
from eyetracker.core.pipeline import EyeTracker
from eyetracker.core.roi import compute_roi_metrics, compute_tge, fixation_aoi_sequence
from eyetracker.core.saccade import detect_saccades
from eyetracker.data.login import ApiLoginService, LocalLoginService
from eyetracker.data.record import (
    ApiRecordService,
    LocalRecordService,
    Record,
    RecordMetrics,
)
from eyetracker.data.settings import Settings
from eyetracker.data.test import ApiTestDao, LocalTestDao, TestData
from eyetracker.ui.pages.calibration import CalibrationScreen
from eyetracker.ui.pages.home import HomeScreen
from eyetracker.ui.pages.test_completion_screen import TestCompletionScreen
from eyetracker.ui.pages.test_instructions_screen import TestInstructionsScreen
from eyetracker.ui.pages.test_run_screen import TestRunScreen


def _macos_camera_auth_status() -> int:
    """Returns AVAuthorizationStatus via ctypes (no pyobjc needed).
    0=not determined, 1=restricted, 2=denied, 3=authorized.
    """
    import ctypes
    import ctypes.util
    libobjc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
    ctypes.cdll.LoadLibrary(
        "/System/Library/Frameworks/AVFoundation.framework/AVFoundation"
    )
    libobjc.objc_getClass.restype = ctypes.c_void_p
    libobjc.objc_getClass.argtypes = [ctypes.c_char_p]
    libobjc.sel_registerName.restype = ctypes.c_void_p
    libobjc.sel_registerName.argtypes = [ctypes.c_char_p]
    # Build NSString @"vide" (AVMediaTypeVideo)
    libobjc.objc_msgSend.restype = ctypes.c_void_p
    libobjc.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p]
    ns_string = libobjc.objc_getClass(b"NSString")
    sel_swus = libobjc.sel_registerName(b"stringWithUTF8String:")
    media_type = libobjc.objc_msgSend(ns_string, sel_swus, b"vide")
    # Call [AVCaptureDevice authorizationStatusForMediaType:]
    libobjc.objc_msgSend.restype = ctypes.c_long
    libobjc.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    av_class = libobjc.objc_getClass(b"AVCaptureDevice")
    sel_auth = libobjc.sel_registerName(b"authorizationStatusForMediaType:")
    return int(libobjc.objc_msgSend(av_class, sel_auth, media_type))


class _CameraPermissionChecker(QObject):
    granted = pyqtSignal()
    denied = pyqtSignal()

    def check(self) -> None:
        if platform.system() != "Darwin":
            return
        import threading
        import cv2

        try:
            status = _macos_camera_auth_status()
        except Exception:
            return

        if status == 3:  # already authorized
            return
        if status in (1, 2):  # restricted or denied
            self.denied.emit()
            return

        # status == 0: not determined — open camera to trigger the system dialog,
        # then wait in a background thread and emit the result.
        def _request() -> None:
            cap = cv2.VideoCapture(0, cv2.CAP_AVFOUNDATION)
            cap.release()
            try:
                new_status = _macos_camera_auth_status()
            except Exception:
                new_status = 3
            if new_status == 3:
                self.granted.emit()
            else:
                self.denied.emit()

        threading.Thread(target=_request, daemon=True).start()


class App:
    """Main application: manages Home and Calibration screens."""

    def __init__(self):
        self._qt_app = QApplication.instance() or QApplication(sys.argv)
        self._qt_app.setStyleSheet("""
            QMessageBox { background-color: #2a2a2a; }
            QMessageBox QLabel { color: #ffffff; }
            QMessageBox QPushButton {
                color: #ffffff;
                background-color: #3a3a3a;
                border: 1px solid #4a4a4a;
                border-radius: 6px;
                padding: 4px 16px;
                min-width: 60px;
            }
            QMessageBox QPushButton:hover { background-color: #4a4a4a; }
            QToolTip {
                background-color: #2c2c2e;
                color: #ffffff;
                border: 1px solid #48484a;
                border-radius: 4px;
                padding: 4px 8px;
            }
        """)
        self._settings = Settings()

        server_url = self._settings.server_url
        self._api_client = None
        if server_url:
            from eyetracker.data.http_client import HttpClient
            self._api_client = HttpClient(server_url, token=self._settings.auth_token)
            self._test_dao = ApiTestDao(self._api_client)
            self._login_service = ApiLoginService(self._api_client)
            self._record_service = ApiRecordService(self._api_client)
        else:
            self._test_dao = LocalTestDao()
            self._login_service = LocalLoginService()
            self._record_service = LocalRecordService()

        _icon_name = "icon.icns" if platform.system() == "Darwin" else "icon.ico"
        _icon_path = Path(__file__).parent / "assets" / _icon_name
        if _icon_path.exists():
            self._qt_app.setWindowIcon(QIcon(str(_icon_path)))

        self._window = QMainWindow()
        self._window.setWindowTitle("EyeTracker")

        self._stack = QStackedWidget()
        self._window.setCentralWidget(self._stack)

        self._home = HomeScreen(
            on_start_calibration=self._go_to_calibration,
            on_start_test_run=self._go_to_test_run,
            on_start_test_run_by_token=self._go_to_test_run_by_token,
            settings=self._settings,
            test_dao=self._test_dao,
            login_service=self._login_service,
            record_service=self._record_service,
            on_monitor_changed=self._move_to_target_screen,
        )
        if self._api_client is not None:
            self._api_client.on_unauthorized = self._home.logout

        self._calibration: CalibrationScreen | None = None
        self._test_run_screen: TestRunScreen | None = None
        self._completion_screen: TestCompletionScreen | None = None
        self._instructions_screen: TestInstructionsScreen | None = None
        self._completion_test_id: str | None = None
        self._completion_via_token: bool = False
        self._pending_test = None
        self._pending_token: str | None = None
        self._pending_login: str | None = None

        self._stack.addWidget(self._home)

    def run(self):
        self._stack.setCurrentWidget(self._home)
        self._move_to_target_screen()
        QTimer.singleShot(0, self._check_camera_permission)
        if self._api_client is not None and self._settings.auth_token:
            QTimer.singleShot(0, self._check_token)
        self._qt_app.exec()

    def _check_camera_permission(self) -> None:
        self._permission_checker = _CameraPermissionChecker()
        self._permission_checker.granted.connect(self._on_camera_permission_granted)
        self._permission_checker.denied.connect(self._on_camera_permission_denied)
        self._permission_checker.check()

    def _on_camera_permission_granted(self) -> None:
        msg = QMessageBox(self._window)
        msg.setWindowTitle("Доступ к камере")
        msg.setText("Доступ к камере получен. Перезапустите приложение.")
        msg.exec()
        self._qt_app.quit()

    def _on_camera_permission_denied(self) -> None:
        msg = QMessageBox(self._window)
        msg.setWindowTitle("Доступ к камере")
        msg.setText(
            "Доступ к камере запрещён. Разрешите доступ в "
            "Системные настройки → Конфиденциальность и безопасность → Камера, "
            "затем перезапустите приложение."
        )
        msg.exec()
        self._qt_app.quit()

    def _check_token(self) -> None:
        """Validate the stored token against /auth/me/role on startup."""
        try:
            resp = self._api_client.get("/auth/me/role")
            role = resp.get("role")
            if role != self._settings.user_role:
                self._settings.user_role = role
        except Exception:
            self._home.logout()

    def _move_to_target_screen(self):
        """Move the window to the monitor chosen in settings.

        NOTE: macOS fullscreen exit is animated and async. We use a hardcoded
        1s delay as a workaround. See TECH_DEBT.md for details.
        """
        name = self._settings.tracking_display_name
        screen = resolve_screen(name)
        if name is not None and screen.name() != name:
            self._settings.tracking_display_name = None

        if self._window.isFullScreen():
            self._window.showNormal()
            QTimer.singleShot(1000, lambda: self._apply_screen(screen))
        else:
            self._apply_screen(screen)

    def _apply_screen(self, screen):
        """Position window on the given screen and go fullscreen."""
        geo = screen.geometry()
        self._window.setGeometry(geo)
        QApplication.processEvents()
        self._window.showFullScreen()

    def _go_to_calibration(self):
        """Navigate Home -> Calibration: fresh tracker + screen each time."""
        if self._calibration is not None:
            self._stack.removeWidget(self._calibration)
            self._calibration.deleteLater()

        self._move_to_target_screen()

        tracker = EyeTracker()
        tracker.params.data_timestep = self._settings.tracking_timestep_ms
        tracker.smoothing_window_size = self._settings.smoothing_window_size
        self._calibration = CalibrationScreen(
            tracker=tracker,
            on_back=self._go_to_home,
            skip_calibration=self._settings.skip_calibration,
        )
        self._stack.addWidget(self._calibration)
        self._stack.setCurrentWidget(self._calibration)
        self._calibration.start()
        if platform.system() == "Darwin":
            QTimer.singleShot(800, self._window.showFullScreen)

    def _go_to_test_run(self, test: TestData):
        """Navigate Home -> Calibration -> Test run."""
        self._pending_test = test

        if self._calibration is not None:
            self._stack.removeWidget(self._calibration)
            self._calibration.deleteLater()

        self._move_to_target_screen()

        # Flush any pending events from window resize/move
        from PyQt6.QtCore import QCoreApplication
        QCoreApplication.processEvents()

        tracker = EyeTracker()
        tracker.params.data_timestep = self._settings.tracking_timestep_ms
        tracker.smoothing_window_size = self._settings.smoothing_window_size
        self._calibration = CalibrationScreen(
            tracker=tracker,
            on_back=self._go_to_home,
            on_finished=self._on_calibration_for_test_done,
            skip_calibration=self._settings.skip_calibration,
        )
        self._stack.addWidget(self._calibration)
        self._stack.setCurrentWidget(self._calibration)
        self._calibration.start()
        if platform.system() == "Darwin":
            QTimer.singleShot(800, self._window.showFullScreen)

    def _on_calibration_for_test_done(self):
        """Called when calibration finishes during test run flow."""
        tracker = None
        if self._calibration is not None:
            self._calibration.stop_ui_only()
            tracker = self._calibration.wg
            self._stack.removeWidget(self._calibration)
            self._calibration.deleteLater()
            self._calibration = None

        if tracker is None or self._pending_test is None:
            self._go_to_home()
            return

        self._test_run_screen = TestRunScreen(
            tracker=tracker,
            test=self._pending_test,
            test_dao=self._test_dao,
            on_finish=self._on_test_run_done,
            on_back=self._go_to_home,
            show_gaze_marker=self._settings.show_gaze_marker,
            image_display_duration_ms=self._settings.image_display_duration_ms,
            fixation_enabled=self._settings.fixation_enabled,
            fixation_k=self._settings.fixation_radius_threshold_k,
            fixation_window_samples=self._settings.fixation_window_size_samples,
        )
        self._stack.addWidget(self._test_run_screen)
        self._stack.setCurrentWidget(self._test_run_screen)
        self._test_run_screen.start()

    def _go_to_test_run_by_token(self, test: TestData, token: str, login: str) -> None:
        """Navigate to test run started by access code: show instructions first."""
        self._pending_token = token
        self._pending_login = login

        if self._instructions_screen is not None:
            self._stack.removeWidget(self._instructions_screen)
            self._instructions_screen.deleteLater()

        self._instructions_screen = TestInstructionsScreen(
            test_name=test.name,
            on_start=lambda: self._start_test_after_instructions(test),
            on_cancel=self._cancel_instructions,
        )
        self._stack.addWidget(self._instructions_screen)
        self._stack.setCurrentWidget(self._instructions_screen)

    def _start_test_after_instructions(self, test: TestData) -> None:
        """Remove instructions screen and proceed to calibration."""
        if self._instructions_screen is not None:
            self._stack.removeWidget(self._instructions_screen)
            self._instructions_screen.deleteLater()
            self._instructions_screen = None
        self._go_to_test_run(test)

    def _cancel_instructions(self) -> None:
        """Return from instructions screen back to home."""
        if self._instructions_screen is not None:
            self._stack.removeWidget(self._instructions_screen)
            self._instructions_screen.deleteLater()
            self._instructions_screen = None
        self._pending_token = None
        self._pending_login = None
        self._stack.setCurrentWidget(self._home)

    def _on_test_run_done(self):
        """Called when all test images have been shown."""
        record = self._build_record()
        if record is not None:
            if self._pending_token:
                self._record_service.save_unauthorized(
                    record, self._pending_token, self._pending_login or ""
                )
            else:
                self._record_service.save(record)

        self._cleanup_test_run()
        self._completion_test_id = self._pending_test.id if self._pending_test else None
        self._completion_via_token = bool(self._pending_token)
        self._pending_test = None
        self._pending_token = None
        self._pending_login = None

        self._show_completion_screen()

    def _show_completion_screen(self):
        """Show the test completion screen."""
        if self._completion_screen is not None:
            self._stack.removeWidget(self._completion_screen)
            self._completion_screen.deleteLater()

        goes_to_test = not self._completion_via_token and self._completion_test_id is not None
        btn_label = "Вернуться к тесту" if goes_to_test else "Вернуться на главный экран"
        self._completion_screen = TestCompletionScreen(on_go_home=self._on_completion_go_home, button_label=btn_label)
        self._stack.addWidget(self._completion_screen)
        self._stack.setCurrentWidget(self._completion_screen)

    def _on_completion_go_home(self):
        """Navigate from completion screen back to home."""
        if self._completion_screen is not None:
            self._stack.removeWidget(self._completion_screen)
            self._completion_screen.deleteLater()
            self._completion_screen = None

        self._stack.setCurrentWidget(self._home)

        test_id = self._completion_test_id
        if not self._completion_via_token and test_id is not None:
            self._home.show_test(test_id)
        else:
            self._home._select_sidebar_item("overview")

        self._completion_test_id = None
        self._completion_via_token = False
        self._home.setFocus()

    def _build_record(self) -> Record | None:
        if self._test_run_screen is None or self._pending_test is None:
            return None

        now = datetime.now(timezone.utc).isoformat()
        started = self._test_run_screen.started_at or now
        finished = self._test_run_screen.finished_at or now

        started_dt = datetime.fromisoformat(started)
        finished_dt = datetime.fromisoformat(finished)
        duration_ms = int((finished_dt - started_dt).total_seconds() * 1000)

        filename, aggregator = self._test_run_screen.get_results()
        timed = self._test_run_screen.get_timed_gaze()

        aggregated = aggregator.get_aggregated()
        groups = []
        for i, g in enumerate(aggregated):
            entry: dict = {"x": g.x, "y": g.y, "count": g.count}
            if i < len(timed):
                entry["time_ms"] = timed[i][2]
            groups.append(entry)

        # Detect fixations offline using I-VT; scale normalized coords to actual screen px
        screen_geo = self._window.screen().geometry()
        vw, vh = float(screen_geo.width()), float(screen_geo.height())
        scaled_pts = [
            {"x": g["x"] * vw, "y": g["y"] * vh, "time_ms": g.get("time_ms", 0)}
            for g in groups
        ]
        fixations = detect_fixations_ivt(scaled_pts)
        for f in fixations:
            f["center"]["x"] /= vw
            f["center"]["y"] /= vh
            f["radius"] /= max(vw, vh)
            for p in f["points"]:
                p["x"] /= vw
                p["y"] /= vh

        first_fix_time = next(
            (fx.get("start_ms") for fx in fixations if fx.get("is_first")), None
        )
        velocities = _compute_velocities(groups)
        raw_saccades = detect_saccades(groups, velocities)
        saccades = [
            {
                "duration_ms": s.duration_ms,
                "points": [
                    {
                        "x": groups[i]["x"],
                        "y": groups[i]["y"],
                        "time_ms": groups[i].get("time_ms"),
                        "velocity": velocities[i],
                    }
                    for i in range(s.start_idx, s.end_idx + 1)
                ],
            }
            for s in raw_saccades
        ]
        roi_metrics = compute_roi_metrics(self._pending_test.aoi, fixations)
        aoi_seq = fixation_aoi_sequence(self._pending_test.aoi, fixations)
        tge = compute_tge(aoi_seq)

        return Record(
            id=uuid.uuid4().hex,
            test_id=self._pending_test.id,
            user_login=self._pending_login or "local",
            started_at=started,
            finished_at=finished,
            duration_ms=duration_ms,
            metrics=RecordMetrics(
                gaze_groups=groups,
                fixations=fixations,
                first_fixation_time_ms=first_fix_time,
                saccades=saccades,
                roi_metrics=roi_metrics,
                aoi_sequence=aoi_seq,
                tge=tge,
            ),
            created_at=now,
        )

    def _cleanup_test_run(self):
        """Stop and remove test run screen."""
        if self._test_run_screen is not None:
            self._test_run_screen.stop()
            self._stack.removeWidget(self._test_run_screen)
            self._test_run_screen.deleteLater()
            self._test_run_screen = None

    def _go_to_home(self):
        """Navigate Calibration/TestRun -> Home: full cleanup."""
        if self._calibration is not None:
            self._calibration.stop()
            self._stack.removeWidget(self._calibration)
            self._calibration.deleteLater()
            self._calibration = None
        self._cleanup_test_run()
        self._pending_test = None
        self._stack.setCurrentWidget(self._home)
        self._home.setFocus()
