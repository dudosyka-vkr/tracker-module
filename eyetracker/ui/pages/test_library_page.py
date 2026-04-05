"""Library page showing all tests as a tile grid."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QPixmap
from PyQt6.QtWidgets import (
    QGridLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from eyetracker.data.test import TestDao, TestData
from eyetracker.ui.theme import (
    BG_MAIN,
    BG_SIDEBAR,
    BORDER_COLOR,
    CORNER_RADIUS,
    FONT_FAMILY,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TILE_GAP,
    TILE_H,
    TILE_W,
)


class TestLibraryPage(QWidget):
    """Grid of test tiles with cover + name. First tile is always '+ New'."""

    test_selected = pyqtSignal(str)  # emits test ID
    create_requested = pyqtSignal()

    def __init__(self, dao: TestDao, parent: QWidget | None = None):
        super().__init__(parent)
        self._dao = dao
        self._cols = 1
        self.setStyleSheet(f"background-color: {BG_MAIN};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # -- header ----------------------------------------------------------
        header = QWidget()
        header.setFixedHeight(80)
        header.setStyleSheet(f"background-color: {BG_MAIN};")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(40, 20, 40, 0)

        title = QLabel("Тесты")
        title.setFont(QFont(FONT_FAMILY, 36, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")
        header_layout.addWidget(title)
        root.addWidget(header)

        # -- scrollable grid -------------------------------------------------
        self._grid_container = QWidget()
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setSpacing(TILE_GAP)
        self._grid_layout.setContentsMargins(40, 20, 40, 20)
        self._grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setWidget(self._grid_container)
        self._scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        root.addWidget(self._scroll)

        self.refresh()

    def refresh(self) -> None:
        """Reload tests from DAO and rebuild the grid."""
        self._tests = self._dao.load_all()
        self._rebuild_grid()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._update_cols()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._update_cols()

    def _update_cols(self) -> None:
        avail = self.width() - 80  # account for margins
        new_cols = max(1, (avail + TILE_GAP) // (TILE_W + TILE_GAP))
        if new_cols != self._cols:
            self._cols = new_cols
            self._rebuild_grid()

    def _rebuild_grid(self) -> None:
        layout = self._grid_layout

        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for c in range(layout.columnCount()):
            layout.setColumnStretch(c, 0)

        cols = max(1, self._cols)

        # "+" tile is always first
        add_tile = self._make_add_tile()
        layout.addWidget(add_tile, 0, 0)

        for idx, test in enumerate(self._tests, start=1):
            row, col = divmod(idx, cols)
            tile = self._make_tile(test)
            layout.addWidget(tile, row, col)

        layout.setColumnStretch(cols, 1)

    def _make_add_tile(self) -> QWidget:
        tile = QPushButton()
        tile.setFixedSize(TILE_W, TILE_H + 36)
        tile.setCursor(Qt.CursorShape.PointingHandCursor)
        tile.setStyleSheet(f"""
            QPushButton {{
                background-color: {BG_SIDEBAR};
                border: 2px dashed {BORDER_COLOR};
                border-radius: {CORNER_RADIUS}px;
                color: {TEXT_SECONDARY};
            }}
            QPushButton:hover {{
                border-color: {TEXT_SECONDARY};
                color: {TEXT_PRIMARY};
            }}
        """)
        tile.clicked.connect(self.create_requested.emit)

        layout = QVBoxLayout(tile)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        plus = QLabel("+")
        plus.setFont(QFont(FONT_FAMILY, 32))
        plus.setAlignment(Qt.AlignmentFlag.AlignCenter)
        plus.setStyleSheet(f"background: transparent; color: {TEXT_SECONDARY};")
        plus.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        hint = QLabel("Создать тест")
        hint.setFont(QFont(FONT_FAMILY, 12))
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet(f"background: transparent; color: {TEXT_SECONDARY};")
        hint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        layout.addWidget(plus)
        layout.addWidget(hint)

        return tile

    def _make_tile(self, test: TestData) -> QWidget:
        tile = QPushButton()
        tile.setFixedSize(TILE_W, TILE_H + 36)
        tile.setCursor(Qt.CursorShape.PointingHandCursor)
        tile.setStyleSheet(f"""
            QPushButton {{
                background-color: {BG_SIDEBAR};
                border: 1px solid {BORDER_COLOR};
                border-radius: {CORNER_RADIUS}px;
            }}
            QPushButton:hover {{
                border-color: {TEXT_SECONDARY};
            }}
        """)
        tile.clicked.connect(lambda _, tid=test.id: self.test_selected.emit(tid))

        layout = QVBoxLayout(tile)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        cover_label = QLabel()
        cover_label.setFixedSize(TILE_W - 8, TILE_H - 8)
        cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cover_label.setStyleSheet(f"background-color: {BG_SIDEBAR}; border-radius: {CORNER_RADIUS - 2}px;")
        cover_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        cover_path = self._dao.get_cover_path(test)
        if cover_path.is_file():
            pm = QPixmap(str(cover_path)).scaled(
                TILE_W - 8, TILE_H - 8,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            cover_label.setPixmap(pm)

        name_label = QLabel(test.name)
        name_label.setFont(QFont(FONT_FAMILY, 12))
        name_label.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        layout.addWidget(cover_label)
        layout.addWidget(name_label)

        return tile
