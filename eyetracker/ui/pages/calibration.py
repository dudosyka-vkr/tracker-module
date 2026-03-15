"""Calibration UI and precision measurement.

Provides a fullscreen PyQt6 widget with 9 calibration points.
The user clicks each point 5 times while looking at it.
After calibration, accuracy is measured and gaze tracking begins.
"""

from __future__ import annotations

import math
import time
import threading
from typing import Callable

import cv2
import numpy as np
from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt6.QtGui import QColor, QFont, QPainter, QImage, QKeyEvent, QMouseEvent
from PyQt6.QtWidgets import QWidget

from eyetracker.core.pipeline import EyeTracker


# ---------------------------------------------------------------------------
# Precision measurement
# ---------------------------------------------------------------------------

class PrecisionCalculator:
    """Stores gaze predictions and calculates accuracy percentage."""

    def __init__(self, window_size: int = 50):
        self.window_size = window_size
        self.x_points: list[float] = [0.0] * window_size
        self.y_points: list[float] = [0.0] * window_size
        self.index = 0
        self.storing = False

    def start_storing(self):
        self.storing = True
        self.index = 0

    def stop_storing(self):
        self.storing = False

    def store_point(self, x: float, y: float):
        if not self.storing:
            return
        self.x_points[self.index % self.window_size] = x
        self.y_points[self.index % self.window_size] = y
        self.index += 1

    def calculate_precision(self, target_x: float, target_y: float) -> float:
        """Calculate precision as a percentage (0-100).

        Measures how close the stored predictions are to the target point.
        """
        n = min(self.index, self.window_size)
        if n == 0:
            return 0.0

        total_distance = 0.0
        for i in range(n):
            dx = self.x_points[i] - target_x
            dy = self.y_points[i] - target_y
            total_distance += math.sqrt(dx * dx + dy * dy)

        avg_distance = total_distance / n
        # Convert to percentage: 100% if distance=0, 0% if distance >= threshold
        precision = max(0.0, 100.0 - avg_distance * 100.0 / 500.0)
        return round(precision, 2)

    def get_points(self) -> tuple[list[float], list[float]]:
        n = min(self.index, self.window_size)
        return self.x_points[:n], self.y_points[:n]


CLICKS_PER_POINT = 5
NUM_POINTS = 9


class CalibrationScreen(QWidget):
    """Fullscreen calibration widget with QPainter rendering."""

    # Phases
    PHASE_INSTRUCTIONS = "instructions"
    PHASE_CALIBRATION = "calibration"
    PHASE_MEASUREMENT = "measurement"
    PHASE_GAZE = "gaze"

    def __init__(self, tracker: EyeTracker, on_back: Callable[[], None]):
        super().__init__()
        self.wg = tracker
        self._on_back = on_back
        self.precision = PrecisionCalculator()

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)

        # Phase
        self._phase = self.PHASE_INSTRUCTIONS

        # Video preview
        self._video_running = False
        self._video_image: QImage | None = None

        # Calibration state
        self._point_clicks: dict[int, int] = {}
        self._points: list[tuple[int, int]] = []
        self._point_colors: dict[int, str] = {}
        self._point_visible: dict[int, bool] = {}
        self._calibrated_count = 0

        # Video preview visibility
        self._show_video = True

        # Gaze dot
        self._gaze_x = 0.0
        self._gaze_y = 0.0
        self._show_gaze_dot = False

        # Accuracy measurement
        self._measuring = False
        self._measure_start = 0.0
        self._accuracy: float | None = None

        # Dynamic train mode
        self._train_mode = False
        self._feedback_markers: list[tuple[float, float, float]] = []

        # Repaint timer
        self._timer = QTimer()
        self._timer.timeout.connect(self.update)

    # ---- Lifecycle -----------------------------------------------------------

    def start(self):
        """Called when navigating to this screen."""
        self.wg.set_screen_size(self.width(), self.height())
        self.wg.begin()
        self.wg.set_gaze_listener(self._on_gaze)
        self._start_video_preview()
        self._phase = self.PHASE_INSTRUCTIONS
        self._timer.start(33)
        self.setFocus()

    def stop(self):
        """Called when leaving this screen."""
        self._video_running = False
        self._timer.stop()
        self.wg.end()

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self.wg.set_screen_size(self.width(), self.height())

    # ---- Qt event overrides --------------------------------------------------

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._paint(painter)
        painter.end()

    def mousePressEvent(self, event: QMouseEvent):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position()
            self._on_click(int(pos.x()), int(pos.y()))

    def keyPressEvent(self, event: QKeyEvent):  # noqa: N802
        self._on_key(event)

    # ---- Painting -----------------------------------------------------------

    def _paint(self, p: QPainter):
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor("black"))

        if self._show_video and self._video_image is not None:
            p.drawImage(10, 10, self._video_image)

        if self._phase == self.PHASE_INSTRUCTIONS:
            self._paint_instructions(p)
        elif self._phase == self.PHASE_CALIBRATION:
            self._paint_calibration(p)
        elif self._phase == self.PHASE_MEASUREMENT:
            self._paint_measurement(p)
        elif self._phase == self.PHASE_GAZE:
            self._paint_gaze(p)

    def _paint_instructions(self, p: QPainter):
        w, h = self.width(), self.height()
        cx, cy = w // 2, h // 2

        p.setPen(QColor("white"))
        p.setFont(QFont("Helvetica", 32, QFont.Weight.Bold))
        p.drawText(QRectF(0, cy - 80, w, 60), Qt.AlignmentFlag.AlignCenter, "КАЛИБРОВКА")

        p.setFont(QFont("Helvetica", 16))
        p.drawText(
            QRectF(0, cy - 10, w, 120),
            Qt.AlignmentFlag.AlignCenter,
            "Кликните по каждой из 9 красных точек 5 раз, глядя на них.\n"
            "Завершённые точки станут жёлтыми.\n\n"
            "Кликните в любое место, чтобы начать.",
        )

    def _paint_calibration(self, p: QPainter):
        for i, (x, y) in enumerate(self._points):
            if not self._point_visible.get(i, True):
                continue
            color = self._point_colors.get(i, "red")
            p.setBrush(QColor(color))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(x, y), 15, 15)

    def _paint_measurement(self, p: QPainter):
        w, h = self.width(), self.height()
        cx, cy = w // 2, h // 2

        p.setBrush(QColor("green"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), 10, 10)

        p.setPen(QColor("white"))
        p.setFont(QFont("Helvetica", 16))
        p.drawText(
            QRectF(0, cy + 30, w, 60),
            Qt.AlignmentFlag.AlignCenter,
            "Смотрите на зелёную точку 5 секунд...\nНе двигайте головой.",
        )

    def _paint_gaze(self, p: QPainter):
        w, h = self.width(), self.height()

        if self._accuracy is not None:
            p.setPen(QColor("white"))
            p.setFont(QFont("Helvetica", 14))
            p.drawText(
                QRectF(w - 220, 10, 210, 30),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"Точность: {self._accuracy}%",
            )

        if self._train_mode:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 180, 0))
            p.drawRoundedRect(QRectF(10, 170, 130, 30), 5, 5)
            p.setPen(QColor("white"))
            p.setFont(QFont("Helvetica", 13, QFont.Weight.Bold))
            p.drawText(QRectF(10, 170, 130, 30), Qt.AlignmentFlag.AlignCenter, "ТРЕНИРОВКА")

        p.setPen(QColor("gray"))
        p.setFont(QFont("Helvetica", 12))
        p.drawText(
            QRectF(0, 15, w, 30),
            Qt.AlignmentFlag.AlignCenter,
            "Отслеживание взгляда (T = тренировка, R = перекалибровка, V = видео, Esc = выход)",
        )

        now = time.time()
        self._feedback_markers = [(x, y, t) for x, y, t in self._feedback_markers if now - t < 0.5]
        for fx, fy, ft in self._feedback_markers:
            alpha = max(0, 1.0 - (now - ft) / 0.5)
            color = QColor(0, 255, 0, int(alpha * 200))
            p.setBrush(color)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(fx, fy), 8, 8)

        if self._show_gaze_dot:
            p.setBrush(QColor("red"))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(self._gaze_x, self._gaze_y), 10, 10)

    # ---- Click handling -----------------------------------------------------

    def _on_click(self, x: int, y: int):
        if self._phase == self.PHASE_INSTRUCTIONS:
            self._start_calibration()
        elif self._phase == self.PHASE_CALIBRATION:
            self._on_calibration_click(x, y)
        elif self._phase == self.PHASE_GAZE and self._train_mode:
            self.wg.record_screen_position(x, y, "click")
            self._feedback_markers.append((float(x), float(y), time.time()))

    def _on_key(self, event: QKeyEvent):
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self._on_back()
        elif key == Qt.Key.Key_V:
            self._show_video = not self._show_video
        elif self._phase == self.PHASE_GAZE:
            if key == Qt.Key.Key_R:
                self._show_gaze_dot = False
                self._train_mode = False
                self._start_calibration()
            elif key == Qt.Key.Key_T:
                self._train_mode = not self._train_mode

    # ---- Calibration logic --------------------------------------------------

    def _start_calibration(self):
        self._phase = self.PHASE_CALIBRATION
        self._calibrated_count = 0
        self._point_clicks = {}
        self._point_colors = {}
        self._point_visible = {}
        self._create_calibration_points()

    def _create_calibration_points(self):
        """Create 9 calibration points in a 3x3 grid.

        Points appear one by one starting from top-center, then clockwise,
        with the center point last.
        """
        w, h = self.width(), self.height()
        margin_x = int(w * 0.1)
        margin_y = int(h * 0.1)

        positions = []
        for row in range(3):
            for col in range(3):
                x = margin_x + col * (w - 2 * margin_x) // 2
                y = margin_y + row * (h - 2 * margin_y) // 2
                positions.append((x, y))

        self._points = positions

        # Order: top-center, then clockwise, center last
        # Grid indices:  0(TL) 1(TC) 2(TR) / 3(ML) 4(C) 5(MR) / 6(BL) 7(BC) 8(BR)
        self._point_order = [1, 2, 5, 8, 7, 6, 3, 0, 4]

        for i in range(len(positions)):
            self._point_clicks[i] = 0
            self._point_colors[i] = "red"
            self._point_visible[i] = (i == self._point_order[0])

    def _on_calibration_click(self, x: int, y: int):
        closest = -1
        min_dist = float("inf")
        for i, (px, py) in enumerate(self._points):
            if self._point_clicks[i] >= CLICKS_PER_POINT:
                continue
            if not self._point_visible.get(i, True):
                continue
            dist = ((x - px) ** 2 + (y - py) ** 2) ** 0.5
            if dist < min_dist and dist < 60:
                min_dist = dist
                closest = i

        if closest < 0:
            return

        px, py = self._points[closest]
        self._point_clicks[closest] += 1

        self.wg.record_screen_position(px, py, "click")

        clicks = self._point_clicks[closest]
        if clicks >= CLICKS_PER_POINT:
            self._point_colors[closest] = "yellow"
            self._calibrated_count += 1

            if self._calibrated_count < NUM_POINTS:
                next_idx = self._point_order[self._calibrated_count]
                self._point_visible[next_idx] = True

            if self._calibrated_count >= NUM_POINTS:
                self._start_measurement()
        else:
            opacity_colors = ["#cc0000", "#dd3300", "#ee6600", "#ff9900", "#ffcc00"]
            self._point_colors[closest] = opacity_colors[min(clicks, len(opacity_colors) - 1)]

    def _start_measurement(self):
        self._phase = self.PHASE_MEASUREMENT
        self._measuring = True
        self.precision.start_storing()
        self._measure_start = time.time()

        QTimer.singleShot(5000, self._finish_measurement)

    def _finish_measurement(self):
        self._measuring = False
        self.precision.stop_storing()

        cx = self.width() // 2
        cy = self.height() // 2
        self._accuracy = self.precision.calculate_precision(cx, cy)

        self._phase = self.PHASE_GAZE
        self._show_gaze_dot = True

    def _on_gaze(self, gaze_data: dict | None, elapsed: float):
        if gaze_data is None:
            return

        x, y = gaze_data["x"], gaze_data["y"]

        if self._measuring:
            self.precision.store_point(x, y)

        if self._show_gaze_dot:
            self._gaze_x = x
            self._gaze_y = y

    # ---- Video preview ------------------------------------------------------

    def _start_video_preview(self):
        self._video_running = True
        self._video_thread = threading.Thread(target=self._update_video, daemon=True)
        self._video_thread.start()

    def _update_video(self):
        while self._video_running:
            frame = self.wg.get_latest_frame()
            if frame is not None:
                preview = cv2.resize(frame, (500, 375))
                preview = cv2.cvtColor(preview, cv2.COLOR_BGR2RGB)

                landmarks = self.wg.get_latest_landmarks()
                if landmarks:
                    h, w = frame.shape[:2]
                    scale_x = 500 / w
                    scale_y = 375 / h
                    for lx, ly in landmarks[:468]:
                        px = int(lx * scale_x)
                        py = int(ly * scale_y)
                        cv2.circle(preview, (px, py), 1, (0, 255, 0), -1)

                h, w, ch = preview.shape
                bytes_per_line = ch * w
                self._video_image = QImage(
                    preview.data, w, h, bytes_per_line, QImage.Format.Format_RGB888
                ).copy()

            time.sleep(0.05)
