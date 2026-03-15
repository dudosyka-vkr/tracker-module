"""Reusable image tile grid widget with a leading '+' button, preview overlay, and drag-to-reorder."""

from __future__ import annotations

from PyQt6.QtCore import QMimeData, QPoint, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QDrag, QFont, QIcon, QKeyEvent, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QGridLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from eyetracker.ui.theme import (
    BG_SIDEBAR,
    BG_SIDEBAR_ACTIVE,
    BORDER_COLOR,
    CORNER_RADIUS,
    ERROR_COLOR,
    FONT_FAMILY,
    TEXT_SECONDARY,
    TILE_GAP,
    TILE_H,
    TILE_W,
)

_DRAG_MIME_TYPE = "application/x-eyetracker-tile-path"


class ImagePreviewOverlay(QWidget):
    """Full-window overlay showing a large image preview with dark backdrop."""

    def __init__(self, pixmap: QPixmap, parent: QWidget):
        super().__init__(parent)
        self._original_pm = pixmap
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        self._close_btn = QPushButton("✕", self)
        self._close_btn.setFixedSize(36, 36)
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(60, 60, 60, 200);
                color: white;
                border: none;
                border-radius: 18px;
                font-size: 18px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(100, 100, 100, 220);
            }
        """)
        self._close_btn.clicked.connect(self.close)

    def show_over_window(self) -> None:
        top = self.parent()
        while top.parent() is not None:
            top = top.parent()
        self.setParent(top)
        self.setGeometry(top.rect())
        self.raise_()
        self.show()
        self.setFocus()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        painter.setOpacity(0.85)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        painter.setOpacity(1.0)

        max_w = int(self.width() * 0.7)
        max_h = int(self.height() * 0.8)
        scaled = self._original_pm.scaled(
            max_w, max_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)
        painter.end()

    def resizeEvent(self, event) -> None:  # noqa: N802
        self._close_btn.move(self.width() - 52, 16)
        super().resizeEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        max_w = int(self.width() * 0.7)
        max_h = int(self.height() * 0.8)
        scaled = self._original_pm.scaled(
            max_w, max_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        img_x = (self.width() - scaled.width()) // 2
        img_y = (self.height() - scaled.height()) // 2
        img_rect = scaled.rect().translated(img_x, img_y)
        if not img_rect.contains(event.pos()):
            self.close()


class _DraggableTile(QWidget):
    """Image tile that supports click-to-preview and drag-to-reorder."""

    preview_requested = pyqtSignal(str)

    def __init__(
        self,
        path: str,
        pixmap: QPixmap | None,
        draggable: bool,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._path = path
        self._pixmap = pixmap
        self._draggable = draggable
        self._drag_start: QPoint | None = None
        self.setFixedSize(TILE_W, TILE_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # Image label (transparent for mouse events — container handles them)
        img = QLabel(self)
        img.setFixedSize(TILE_W, TILE_H)
        img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        img.setStyleSheet(f"""
            QLabel {{
                background-color: {BG_SIDEBAR};
                border: none;
                border-radius: {CORNER_RADIUS}px;
            }}
        """)
        img.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        if pixmap:
            img.setPixmap(pixmap)
        self._img_label = img

    def set_highlight(self, on: bool) -> None:
        border = f"2px solid {BG_SIDEBAR_ACTIVE}" if on else "none"
        self._img_label.setStyleSheet(f"""
            QLabel {{
                background-color: {BG_SIDEBAR};
                border: {border};
                border-radius: {CORNER_RADIUS}px;
            }}
        """)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.pos()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if (
            self._draggable
            and self._drag_start is not None
            and (event.pos() - self._drag_start).manhattanLength()
            > QApplication.startDragDistance()
        ):
            drag = QDrag(self)
            mime = QMimeData()
            mime.setData(_DRAG_MIME_TYPE, self._path.encode("utf-8"))
            drag.setMimeData(mime)

            # Semi-transparent drag pixmap
            if self._pixmap:
                thumb = self._pixmap.scaled(
                    TILE_W // 2, TILE_H // 2,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                drag.setPixmap(thumb)
                drag.setHotSpot(QPoint(thumb.width() // 2, thumb.height() // 2))

            self._drag_start = None
            drag.exec(Qt.DropAction.MoveAction)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._drag_start is not None:
            # No drag happened — treat as click → preview
            self._drag_start = None
            self.preview_requested.emit(self._path)


class ImageGridWidget(QWidget):
    """Tile grid showing a '+' add-button followed by 16:9 image thumbnails."""

    add_clicked = pyqtSignal()
    images_changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None, readonly: bool = False):
        super().__init__(parent)
        self._paths: list[str] = []
        self._pixmaps: dict[str, QPixmap] = {}
        self._cols = 1
        self._readonly = readonly
        self._drop_target_index: int | None = None
        self._tiles: list[_DraggableTile] = []

        self.setAcceptDrops(True)

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
            TILE_W, TILE_H,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._rebuild_grid()
        self.images_changed.emit()
        return True

    def get_image_paths(self) -> list[str]:
        return list(self._paths)

    def set_readonly(self, readonly: bool) -> None:
        if self._readonly != readonly:
            self._readonly = readonly
            self._rebuild_grid()

    def set_images(self, paths: list[str]) -> None:
        """Bulk-load images, replacing current contents."""
        self._paths.clear()
        self._pixmaps.clear()
        for path in paths:
            pm = QPixmap(path)
            if not pm.isNull():
                self._paths.append(path)
                self._pixmaps[path] = pm.scaled(
                    TILE_W, TILE_H,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
        self._rebuild_grid()

    def remove_image(self, path: str) -> None:
        """Remove an image by path."""
        if path in self._paths:
            self._paths.remove(path)
            self._pixmaps.pop(path, None)
            self._rebuild_grid()
            self.images_changed.emit()

    def clear(self) -> None:
        self._paths.clear()
        self._pixmaps.clear()
        self._rebuild_grid()

    # -- drag & drop ---------------------------------------------------------

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if self._readonly:
            return
        if event.mimeData().hasFormat(_DRAG_MIME_TYPE):
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if self._readonly:
            return
        if not event.mimeData().hasFormat(_DRAG_MIME_TYPE):
            return
        event.acceptProposedAction()
        target = self._index_at_pos(event.position().toPoint())
        if target != self._drop_target_index:
            self._clear_highlight()
            self._drop_target_index = target
            if target is not None and target < len(self._tiles):
                self._tiles[target].set_highlight(True)

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        self._clear_highlight()
        self._drop_target_index = None

    def dropEvent(self, event) -> None:  # noqa: N802
        if self._readonly:
            return
        mime = event.mimeData()
        if not mime.hasFormat(_DRAG_MIME_TYPE):
            return

        source_path = bytes(mime.data(_DRAG_MIME_TYPE)).decode("utf-8")
        if source_path not in self._paths:
            return

        target_idx = self._index_at_pos(event.position().toPoint())
        source_idx = self._paths.index(source_path)

        self._clear_highlight()
        self._drop_target_index = None

        if target_idx is None or target_idx == source_idx:
            return

        # Reorder
        self._paths.pop(source_idx)
        self._paths.insert(target_idx, source_path)
        self._rebuild_grid()
        self.images_changed.emit()
        event.acceptProposedAction()

    def _index_at_pos(self, pos: QPoint) -> int | None:
        """Return the image index (into self._paths) at the given widget position."""
        offset = 0 if self._readonly else 1
        for i, tile in enumerate(self._tiles):
            # Map tile geometry to grid widget coordinates
            tile_pos = tile.parent().mapTo(self, QPoint(0, 0)) if tile.parent() != self else tile.pos()
            tile_rect = tile.rect().translated(tile_pos)
            if tile_rect.contains(pos):
                return i
        # If past all tiles, return last index
        if self._tiles and pos.y() >= 0:
            return len(self._tiles) - 1
        return None

    def _clear_highlight(self) -> None:
        for tile in self._tiles:
            tile.set_highlight(False)

    # -- internal ------------------------------------------------------------

    def _remove_image(self, path: str) -> None:
        self.remove_image(path)

    def _preview_image(self, path: str) -> None:
        pm = QPixmap(path)
        if pm.isNull():
            return
        overlay = ImagePreviewOverlay(pm, self)
        overlay.show_over_window()

    def resizeEvent(self, event):  # noqa: N802
        new_cols = max(1, (self.width() - TILE_GAP) // (TILE_W + TILE_GAP))
        if new_cols != self._cols:
            self._cols = new_cols
            self._rebuild_grid()
        super().resizeEvent(event)

    def _rebuild_grid(self) -> None:
        layout = self._grid_layout
        self._tiles.clear()

        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        cols = max(1, self._cols)

        for c in range(layout.columnCount()):
            layout.setColumnStretch(c, 0)

        offset = 0
        if not self._readonly:
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
            offset = 1

        for idx, path in enumerate(self._paths):
            row, col = divmod(idx + offset, cols)
            pm = self._pixmaps.get(path)

            container = QWidget()
            container.setFixedSize(TILE_W, TILE_H)

            draggable = not self._readonly
            tile = _DraggableTile(path, pm, draggable=draggable, parent=container)
            tile.preview_requested.connect(self._preview_image)
            self._tiles.append(tile)

            if not self._readonly:
                rm_btn = QPushButton("✕", container)
                rm_btn.setFixedSize(24, 24)
                rm_btn.move(TILE_W - 28, 4)
                rm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                rm_btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {ERROR_COLOR};
                        color: white;
                        border: none;
                        border-radius: 12px;
                        font-size: 14px;
                        font-weight: bold;
                    }}
                    QPushButton:hover {{
                        background-color: #cc362e;
                    }}
                """)
                rm_btn.clicked.connect(lambda _, p=path: self._remove_image(p))
                rm_btn.raise_()

            layout.addWidget(container, row, col)

        layout.setColumnStretch(cols, 1)
