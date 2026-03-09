"""Home screen with sidebar and content area."""

from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QKeyEvent
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from eyetracker.theme import (
    BG_MAIN,
    BG_SIDEBAR,
    BG_SIDEBAR_ACTIVE,
    BG_SIDEBAR_HOVER,
    BORDER_COLOR,
    BUTTON_BG,
    BUTTON_HOVER,
    CORNER_RADIUS,
    FONT_FAMILY,
    SIDEBAR_ITEM_HEIGHT,
    SIDEBAR_PADDING,
    SIDEBAR_WIDTH,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

_SIDEBAR_ITEMS = [
    {"id": "overview", "title": "Обзор", "icon": "⌂"},
    {"id": "devices", "title": "Устройства", "icon": "⎚"},
    {"id": "calibration", "title": "Калибровка", "icon": "◎"},
    {"id": "settings", "title": "Настройки", "icon": "⚙"},
    {"id": "help", "title": "Помощь", "icon": "?"},
]


class HomeScreen(QWidget):
    """Home screen with a macOS-style sidebar and content area."""

    def __init__(self, on_start_calibration: Callable[[], None]):
        super().__init__()
        self._on_start = on_start_calibration
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_sidebar())

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFixedWidth(1)
        sep.setStyleSheet(f"background-color: {BORDER_COLOR};")
        layout.addWidget(sep)

        layout.addWidget(self._build_content(), stretch=1)

    # ---- Sidebar -------------------------------------------------------------

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setFixedWidth(SIDEBAR_WIDTH)
        sidebar.setStyleSheet(f"background-color: {BG_SIDEBAR};")

        vbox = QVBoxLayout(sidebar)
        vbox.setContentsMargins(SIDEBAR_PADDING, SIDEBAR_PADDING, SIDEBAR_PADDING, SIDEBAR_PADDING)
        vbox.setSpacing(4)

        self._btn_group = QButtonGroup(self)
        self._btn_group.setExclusive(True)

        for item in _SIDEBAR_ITEMS:
            btn = QPushButton(f"  {item['icon']}   {item['title']}")
            btn.setFixedHeight(SIDEBAR_ITEM_HEIGHT)
            btn.setCheckable(True)
            btn.setFlat(True)
            btn.setFont(QFont(FONT_FAMILY, 13))
            btn.setStyleSheet(f"""
                QPushButton {{
                    color: {TEXT_PRIMARY};
                    text-align: left;
                    padding-left: 12px;
                    border: none;
                    border-radius: {CORNER_RADIUS}px;
                    background-color: transparent;
                }}
                QPushButton:hover {{
                    background-color: {BG_SIDEBAR_HOVER};
                }}
                QPushButton:checked {{
                    background-color: {BG_SIDEBAR_ACTIVE};
                    color: white;
                }}
            """)
            btn.clicked.connect(lambda checked, iid=item["id"]: self._on_sidebar_click(iid))
            self._btn_group.addButton(btn)
            vbox.addWidget(btn)

            if item["id"] == "overview":
                btn.setChecked(True)

        vbox.addStretch()
        return sidebar

    def _on_sidebar_click(self, item_id: str):
        if item_id == "calibration":
            self._on_start()

    # ---- Content area --------------------------------------------------------

    def _build_content(self) -> QWidget:
        content = QWidget()
        content.setStyleSheet(f"background-color: {BG_MAIN};")

        vbox = QVBoxLayout(content)
        vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("EyeTracker")
        title.setFont(QFont(FONT_FAMILY, 36, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        desc = QLabel("Система отслеживания взгляда\nчерез веб-камеру")
        desc.setFont(QFont(FONT_FAMILY, 16))
        desc.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)

        btn = QPushButton("Начать калибровку")
        btn.setFixedSize(220, 44)
        btn.setFont(QFont(FONT_FAMILY, 15, QFont.Weight.Bold))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(self._on_start)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {BUTTON_BG};
                color: white;
                border: none;
                border-radius: {CORNER_RADIUS}px;
            }}
            QPushButton:hover {{
                background-color: {BUTTON_HOVER};
            }}
        """)

        vbox.addWidget(title)
        vbox.addSpacing(10)
        vbox.addWidget(desc)
        vbox.addSpacing(30)
        vbox.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)

        return content

    # ---- Keys ----------------------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent):  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            QApplication.quit()
