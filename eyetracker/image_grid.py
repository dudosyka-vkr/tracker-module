"""Reusable image tile grid widget with a leading '+' button."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QPixmap
from PyQt6.QtWidgets import (
    QGridLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from eyetracker.theme import (
    BG_SIDEBAR,
    BORDER_COLOR,
    CORNER_RADIUS,
    FONT_FAMILY,
    TEXT_SECONDARY,
    TILE_GAP,
    TILE_H,
    TILE_W,
)


class ImageGridWidget(QWidget):
    """Tile grid showing a '+' add-button followed by 16:9 image thumbnails."""

    add_clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._paths: list[str] = []
        self._pixmaps: dict[str, QPixmap] = {}
        self._cols = 1

        self._grid_layout = QGridLayout(self)
        self._grid_layout.setSpacing(TILE_GAP)
        self._grid_layout.setContentsMargins(0, 0, 0, 0)

        self._rebuild_grid()

    # -- public API ----------------------------------------------------------

    def add_image(self, path: str) -> bool:
        """Add an image. Returns False if the pixmap cannot be loaded."""
        pm = QPixmap(path)
        if pm.isNull():
            return False
        self._paths.append(path)
        self._pixmaps[path] = pm.scaled(
            TILE_W,
            TILE_H,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._rebuild_grid()
        return True

    def get_image_paths(self) -> list[str]:
        return list(self._paths)

    def clear(self) -> None:
        self._paths.clear()
        self._pixmaps.clear()
        self._rebuild_grid()

    # -- internal ------------------------------------------------------------

    def resizeEvent(self, event):  # noqa: N802
        new_cols = max(1, (self.width() - TILE_GAP) // (TILE_W + TILE_GAP))
        if new_cols != self._cols:
            self._cols = new_cols
            self._rebuild_grid()
        super().resizeEvent(event)

    def _rebuild_grid(self) -> None:
        layout = self._grid_layout
        # Clear existing widgets
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        cols = max(1, self._cols)

        # Reset column stretches from previous build
        for c in range(layout.columnCount()):
            layout.setColumnStretch(c, 0)

        # '+' button always first
        add_btn = QPushButton("+")
        add_btn.setFixedSize(TILE_W, TILE_H)
        add_btn.setFont(QFont(FONT_FAMILY, 28))
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {BG_SIDEBAR};
                color: {TEXT_SECONDARY};
                border: 2px dashed {BORDER_COLOR};
                border-radius: {CORNER_RADIUS}px;
            }}
            QPushButton:hover {{
                border-color: {TEXT_SECONDARY};
            }}
        """)
        add_btn.clicked.connect(self.add_clicked.emit)
        layout.addWidget(add_btn, 0, 0)

        for idx, path in enumerate(self._paths):
            row, col = divmod(idx + 1, cols)
            pm = self._pixmaps.get(path)
            tile = QLabel()
            tile.setFixedSize(TILE_W, TILE_H)
            tile.setAlignment(Qt.AlignmentFlag.AlignCenter)
            tile.setStyleSheet(f"""
                QLabel {{
                    background-color: {BG_SIDEBAR};
                    border-radius: {CORNER_RADIUS}px;
                }}
            """)
            if pm:
                tile.setPixmap(pm)
            layout.addWidget(tile, row, col)

        # Push tiles to the left by stretching the last column
        layout.setColumnStretch(cols, 1)
