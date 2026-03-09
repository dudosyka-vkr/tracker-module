"""Application shell with QStackedWidget navigation."""

from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication, QMainWindow, QStackedWidget

from eyetracker.calibration import CalibrationScreen
from eyetracker.home import HomeScreen
from eyetracker.pipeline import EyeTracker


class App:
    """Main application: manages Home and Calibration screens."""

    def __init__(self):
        self._qt_app = QApplication.instance() or QApplication(sys.argv)

        self._window = QMainWindow()
        self._window.setWindowTitle("EyeTracker")

        self._stack = QStackedWidget()
        self._window.setCentralWidget(self._stack)

        self._home = HomeScreen(on_start_calibration=self._go_to_calibration)
        self._calibration: CalibrationScreen | None = None

        self._stack.addWidget(self._home)

    def run(self):
        self._stack.setCurrentWidget(self._home)
        self._window.showFullScreen()
        self._qt_app.exec()

    def _go_to_calibration(self):
        """Navigate Home -> Calibration: fresh tracker + screen each time."""
        if self._calibration is not None:
            self._stack.removeWidget(self._calibration)
            self._calibration.deleteLater()

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
