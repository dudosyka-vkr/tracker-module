"""Screen shown after a test run completes successfully."""

from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from eyetracker.ui.theme import (
    BG_MAIN,
    BUTTON_BG,
    BUTTON_HOVER,
    CORNER_RADIUS,
    FONT_FAMILY,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


class TestCompletionScreen(QWidget):
    """Fullscreen completion screen displayed after test results are saved."""

    def __init__(self, on_go_home: Callable[[], None], button_label: str = "Вернуться на главный экран"):
        super().__init__()
        self._on_go_home = on_go_home
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"background-color: {BG_MAIN};")

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(32)

        title = QLabel("Тест был успешно пройден, данные записаны, спасибо")
        title.setFont(QFont(FONT_FAMILY, 26, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setWordWrap(True)
        layout.addWidget(title)

        btn = QPushButton(button_label)
        btn.setFont(QFont(FONT_FAMILY, 15))
        btn.setFixedHeight(48)
        btn.setFixedWidth(320)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {BUTTON_BG};
                color: {TEXT_PRIMARY};
                border: none;
                border-radius: {CORNER_RADIUS}px;
            }}
            QPushButton:hover {{
                background-color: {BUTTON_HOVER};
            }}
        """)
        btn.clicked.connect(on_go_home)
        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)
