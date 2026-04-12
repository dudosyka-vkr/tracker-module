"""Test run screen: single image display with gaze tracking."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import Qt, QPointF, QRectF, QTimer
from PyQt6.QtGui import QColor, QFont, QImage, QKeyEvent, QPainter
from PyQt6.QtWidgets import QWidget

from eyetracker.core.face_emotion import FaceEmotionRecognition
from eyetracker.core.fixation import FixationDetector
from eyetracker.core.metrics import GazeMetricsAggregator
from eyetracker.core.pipeline import EyeTracker
from eyetracker.data.test import TestDao, TestData


class TestRunScreen(QWidget):
    """Fullscreen widget that shows the test image and collects gaze data."""

    def __init__(
        self,
        tracker: EyeTracker,
        test: TestData,
        test_dao: TestDao,
        on_finish: Callable[[], None],
        on_back: Callable[[], None],
        show_gaze_marker: bool = False,
        image_display_duration_ms: int = 5000,
        fixation_enabled: bool = True,
        fixation_k: float = 80.0,
        fixation_window_samples: int = 10,
    ):
        super().__init__()
        self._tracker = tracker
        self._test = test
        self._test_dao = test_dao
        self._on_finish = on_finish
        self._on_back = on_back
        self._show_gaze_marker = show_gaze_marker
        self._fixation_enabled = fixation_enabled
        self._fixation_k = fixation_k
        self._fixation_window_samples = fixation_window_samples

        self._image_path: Path = test_dao.get_image_path(test)
        self._aggregator = GazeMetricsAggregator()
        self._fixations: list[dict] = []
        self._timed_gaze: list[tuple[float, float, int]] = []
        self._first_fixation_recorded = False
        self._fixation_detector: FixationDetector | None = None
        self._emotion_recognizer = FaceEmotionRecognition()

        self._current_image: QImage | None = None
        self._started_at: str | None = None
        self._finished_at: str | None = None
        self._image_started_at: datetime | None = None
        self._screen_w = 0
        self._screen_h = 0
        self._gaze_x: float = 0.0
        self._gaze_y: float = 0.0

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._image_timer = QTimer()
        self._image_timer.setInterval(image_display_duration_ms)
        self._image_timer.timeout.connect(self._finish)

        self._repaint_timer = QTimer()
        self._repaint_timer.timeout.connect(self.update)

    @property
    def started_at(self) -> str | None:
        return self._started_at

    @property
    def finished_at(self) -> str | None:
        return self._finished_at

    def get_results(self) -> tuple[str, GazeMetricsAggregator]:
        return (self._test.image_filename, self._aggregator)

    def get_fixations(self) -> list[dict]:
        return self._fixations

    def get_timed_gaze(self) -> list[tuple[float, float, int]]:
        return list(self._timed_gaze)

    def start(self) -> None:
        self._started_at = datetime.now(timezone.utc).isoformat()
        self._screen_w = self.width()
        self._screen_h = self.height()
        self._image_started_at = datetime.now(timezone.utc)
        self._current_image = QImage(str(self._image_path))
        if self._fixation_enabled:
            self._fixation_detector = FixationDetector(
                k=self._fixation_k,
                window_size_samples=self._fixation_window_samples,
                on_fixation=self._on_fixation_detected,
            )
        self._first_fixation_recorded = False
        self._tracker.set_gaze_listener(self._on_gaze)
        self._image_timer.start()
        self._repaint_timer.start(33)
        self.setFocus()

    def stop(self) -> None:
        self._image_timer.stop()
        self._repaint_timer.stop()
        self._tracker.end()

    def stop_tracking_only(self) -> None:
        self._image_timer.stop()
        self._repaint_timer.stop()

    def _finish(self) -> None:
        self._finished_at = datetime.now(timezone.utc).isoformat()
        self._image_timer.stop()
        self._repaint_timer.stop()
        self._on_finish()

    def _on_gaze(self, gaze_data: dict | None, elapsed: float) -> None:
        if gaze_data is None:
            return
        x, y = gaze_data["x"], gaze_data["y"]
        self._gaze_x = x
        self._gaze_y = y
        self._aggregator.add_point(x, y, self._screen_w, self._screen_h)
        if self._image_started_at is not None:
            time_ms = int(
                (datetime.now(timezone.utc) - self._image_started_at).total_seconds() * 1000
            )
            self._timed_gaze.append((x, y, time_ms))
        if self._fixation_detector is not None:
            self._fixation_detector.on_gaze_point(x, y)

    def _on_fixation_detected(self, fixation: dict) -> None:
        fixation["is_first"] = not self._first_fixation_recorded
        if not self._first_fixation_recorded:
            self._first_fixation_recorded = True
        if self._image_started_at is not None:
            fixation["time_ms"] = int(
                (datetime.now(timezone.utc) - self._image_started_at).total_seconds() * 1000
            )
        fixation["emotion"] = self._emotion_recognizer.get_emotion_at(
            fixation["center"]["x"], fixation["center"]["y"]
        )
        # Normalize center to [0, 1] so the detail page can render without screen dims
        sw = self._screen_w or 1
        sh = self._screen_h or 1
        fixation["center"] = {
            "x": fixation["center"]["x"] / sw,
            "y": fixation["center"]["y"] / sh,
        }
        self._fixations.append(fixation)

    # ---- Rendering -----------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor("black"))

        if self._current_image and not self._current_image.isNull():
            img = self._current_image.scaled(
                w, h,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (w - img.width()) // 2
            y = (h - img.height()) // 2
            p.drawImage(x, y, img)

        if self._show_gaze_marker:
            p.setBrush(QColor("red"))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(self._gaze_x, self._gaze_y), 10, 10)

        p.end()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self._on_back()
        else:
            super().keyPressEvent(event)
