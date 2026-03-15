"""Application shell with QStackedWidget navigation."""

from __future__ import annotations

import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QMainWindow, QStackedWidget

from eyetracker.core.monitor import resolve_screen
from eyetracker.core.pipeline import EyeTracker
from eyetracker.data.local_test_dao import LocalTestDao
from eyetracker.data.login_service import LocalLoginService
from eyetracker.data.settings import Settings
from eyetracker.ui.pages.calibration import CalibrationScreen
from eyetracker.ui.pages.home import HomeScreen


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
        """)
        self._settings = Settings()
        self._test_dao = LocalTestDao()
        self._login_service = LocalLoginService()

        self._window = QMainWindow()
        self._window.setWindowTitle("EyeTracker")

        self._stack = QStackedWidget()
        self._window.setCentralWidget(self._stack)

        self._home = HomeScreen(
            on_start_calibration=self._go_to_calibration,
            settings=self._settings,
            test_dao=self._test_dao,
            login_service=self._login_service,
            on_monitor_changed=self._move_to_target_screen,
        )
        self._calibration: CalibrationScreen | None = None

        self._stack.addWidget(self._home)

    def run(self):
        self._stack.setCurrentWidget(self._home)
        self._move_to_target_screen()
        self._qt_app.exec()

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
        self._calibration = CalibrationScreen(tracker=tracker, on_back=self._go_to_home)
        self._stack.addWidget(self._calibration)
        self._stack.setCurrentWidget(self._calibration)
        self._calibration.start()

    def _go_to_home(self):
        """Navigate Calibration -> Home: full cleanup."""
        if self._calibration is not None:
            self._calibration.stop()
            self._stack.removeWidget(self._calibration)
            self._calibration.deleteLater()
            self._calibration = None
        self._stack.setCurrentWidget(self._home)
        self._home.setFocus()
