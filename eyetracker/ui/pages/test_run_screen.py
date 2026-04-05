"""Test run screen: sequential image display with gaze tracking."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import Qt, QPointF, QRectF, QTimer
from PyQt6.QtGui import QColor, QFont, QImage, QKeyEvent, QPainter
from PyQt6.QtWidgets import QWidget

from eyetracker.core.metrics import GazeMetricsAggregator
from eyetracker.core.pipeline import EyeTracker
from eyetracker.data.test import TestDao, TestData


class TestRunScreen(QWidget):
    """Fullscreen widget that shows test images and collects gaze data."""

    def __init__(
        self,
        tracker: EyeTracker,
        test: TestData,
        test_dao: TestDao,
        on_finish: Callable[[], None],
        on_back: Callable[[], None],
        show_gaze_marker: bool = False,
    ):
        super().__init__()
        self._tracker = tracker
        self._test = test
        self._test_dao = test_dao
        self._on_finish = on_finish
        self._on_back = on_back
        self._show_gaze_marker = show_gaze_marker

        self._images: list[Path] = [
            test_dao.get_image_path(test, fn) for fn in test.image_filenames
        ]
        self._aggregators: list[GazeMetricsAggregator] = [
            GazeMetricsAggregator() for _ in self._images
        ]
        self._current_index = 0
        self._current_image: QImage | None = None
        self._started_at: str | None = None
        self._finished_at: str | None = None
        self._screen_w = 0
        self._screen_h = 0
        self._gaze_x: float = 0.0
        self._gaze_y: float = 0.0

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._image_timer = QTimer()
        self._image_timer.setInterval(5000)
        self._image_timer.timeout.connect(self._advance_image)

        self._repaint_timer = QTimer()
        self._repaint_timer.timeout.connect(self.update)

    @property
    def started_at(self) -> str | None:
        return self._started_at

    @property
    def finished_at(self) -> str | None:
        return self._finished_at

    def get_results(self) -> list[tuple[str, GazeMetricsAggregator]]:
        return list(zip(self._test.image_filenames, self._aggregators))

    def start(self) -> None:
        if not self._images:
            self._on_finish()
            return
        self._started_at = datetime.now(timezone.utc).isoformat()
        self._current_index = 0
        self._screen_w = self.width()
        self._screen_h = self.height()
        self._load_current_image()
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

    def _load_current_image(self) -> None:
        path = self._images[self._current_index]
        self._current_image = QImage(str(path))

    def _advance_image(self) -> None:
        self._current_index += 1
        if self._current_index >= len(self._images):
            self._finished_at = datetime.now(timezone.utc).isoformat()
            self._image_timer.stop()
            self._repaint_timer.stop()
            self._on_finish()
            return
        self._load_current_image()

    def _on_gaze(self, gaze_data: dict | None, elapsed: float) -> None:
        if gaze_data is None:
            return
        x, y = gaze_data["x"], gaze_data["y"]
        self._gaze_x = x
        self._gaze_y = y
        if self._current_index >= len(self._aggregators):
            return
        self._aggregators[self._current_index].add_point(
            x, y, self._screen_w, self._screen_h
        )

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

        total = len(self._images)
        current = min(self._current_index + 1, total)
        p.setPen(QColor("white"))
        p.setFont(QFont("Helvetica", 14))
        p.drawText(
            QRectF(w - 220, 10, 210, 30),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            f"Изображение {current}/{total}",
        )

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
