"""Fullscreen instruction screen shown before a token-based test run."""

from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QKeyEvent
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from eyetracker.ui.theme import (
    BG_MAIN,
    BG_SIDEBAR,
    BG_SIDEBAR_HOVER,
    BORDER_COLOR,
    BUTTON_BG,
    BUTTON_HOVER,
    CORNER_RADIUS,
    FONT_FAMILY,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

_STEPS = [
    ("1. Калибровка",
     "Сначала пройдёт калибровка камеры. На экране будут появляться точки — "
     "смотрите на каждую из них и кликайте мышкой. Старайтесь держать голову неподвижно."),
    ("2. Прохождение теста",
     "После калибровки на экране будут последовательно показаны изображения. "
     "Просто смотрите на каждое — ничего нажимать не нужно. "
     "Изображение сменится автоматически через отведённое время."),
    ("3. Завершение",
     "После просмотра всех изображений тест завершится автоматически "
     "и результаты будут сохранены."),
]


class TestInstructionsScreen(QWidget):
    """Shown to a participant before calibration starts for a token-based test."""

    def __init__(self, test_name: str, on_start: Callable[[], None], on_cancel: Callable[[], None] = lambda: None):
        super().__init__()
        self._on_cancel = on_cancel
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"background-color: {BG_MAIN};")

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(0)
        layout.setContentsMargins(80, 60, 80, 60)

        title = QLabel(f"Тест «{test_name}»")
        title.setFont(QFont(FONT_FAMILY, 28, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("Перед началом ознакомьтесь с порядком прохождения")
        subtitle.setFont(QFont(FONT_FAMILY, 15))
        subtitle.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        layout.addSpacing(40)

        for step_title, step_body in _STEPS:
            step_title_lbl = QLabel(step_title)
            step_title_lbl.setFont(QFont(FONT_FAMILY, 16, QFont.Weight.Bold))
            step_title_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")
            layout.addWidget(step_title_lbl)

            step_body_lbl = QLabel(step_body)
            step_body_lbl.setFont(QFont(FONT_FAMILY, 14))
            step_body_lbl.setWordWrap(True)
            step_body_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")
            layout.addWidget(step_body_lbl)

            layout.addSpacing(24)

        layout.addSpacing(16)

        btn = QPushButton("Начать калибровку")
        btn.setFont(QFont(FONT_FAMILY, 15, QFont.Weight.Bold))
        btn.setFixedHeight(52)
        btn.setFixedWidth(280)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
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
        btn.clicked.connect(on_start)

        cancel_btn = QPushButton("Отмена")
        cancel_btn.setFont(QFont(FONT_FAMILY, 15))
        cancel_btn.setFixedHeight(52)
        cancel_btn.setFixedWidth(280)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {BG_SIDEBAR};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER_COLOR};
                border-radius: {CORNER_RADIUS}px;
            }}
            QPushButton:hover {{
                background-color: {BG_SIDEBAR_HOVER};
            }}
        """)
        cancel_btn.clicked.connect(on_cancel)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(16)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(btn)
        layout.addLayout(btn_row)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self._on_cancel()
        else:
            super().keyPressEvent(event)
