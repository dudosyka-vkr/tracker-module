"""Reusable image tile grid widget with a leading '+' button, preview overlay, and drag-to-reorder."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QMimeData, QPoint, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QDrag, QFont, QIcon, QKeyEvent, QPainter, QPen, QPixmap, QPolygon
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QGridLayout,
    QLabel,
    QLineEdit,
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

    roi_saved = pyqtSignal(str, list)

    def __init__(
        self,
        pixmap: QPixmap,
        roi_editing: bool = False,
        existing_rois: list[dict] | None = None,
        image_filename: str = "",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._original_pm = pixmap
        self._roi_editing = roi_editing
        self._existing_rois: list[dict] = existing_rois or []
        self._image_filename = image_filename
        self._mode = "viewing"
        self._polygon_closed = False
        self._points: list[tuple[float, float]] = []
        self._cursor_pos: QPoint | None = None
        self._current_color = QColor(0, 220, 100)
        self._selected_roi_idx: int | None = None
        self.setMouseTracking(True)
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

        _btn_style = "border: none; border-radius: 8px; padding: 8px 20px;"
        _font = QFont("SF Pro Display", 13)

        self._add_btn = QPushButton("Добавить область интереса", self)
        self._add_btn.setFont(_font)
        self._add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_btn.setStyleSheet(f"""
            QPushButton {{ background-color: #2563eb; color: white; {_btn_style} }}
            QPushButton:hover {{ background-color: #1d4ed8; }}
        """)
        self._add_btn.clicked.connect(self._enter_drawing_mode)
        self._add_btn.setVisible(roi_editing)

        self._name_input = QLineEdit(self)
        self._name_input.setFont(_font)
        self._name_input.setPlaceholderText("Название области...")
        self._name_input.setStyleSheet("""
            QLineEdit {
                background-color: rgba(40, 40, 40, 210);
                color: white;
                border: 1px solid #4b5563;
                border-radius: 8px;
                padding: 6px 12px;
            }
        """)
        self._name_input.textChanged.connect(self._on_name_changed)
        self._name_input.installEventFilter(self)
        self._name_input.setVisible(False)

        self._save_btn = QPushButton("Сохранить", self)
        self._save_btn.setFont(_font)
        self._save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save_btn.setStyleSheet(f"""
            QPushButton {{ background-color: #16a34a; color: white; {_btn_style} }}
            QPushButton:hover {{ background-color: #15803d; }}
            QPushButton:disabled {{ background-color: #374151; color: #6b7280; }}
        """)
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._on_save_clicked)
        self._save_btn.setVisible(False)

        self._cancel_btn = QPushButton("Отмена", self)
        self._cancel_btn.setFont(_font)
        self._cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel_btn.setStyleSheet(f"""
            QPushButton {{ background-color: #6b7280; color: white; {_btn_style} }}
            QPushButton:hover {{ background-color: #4b5563; }}
        """)
        self._cancel_btn.clicked.connect(self._on_cancel_clicked)
        self._cancel_btn.setVisible(False)

        self._delete_btn = QPushButton("Удалить", self)
        self._delete_btn.setFont(_font)
        self._delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._delete_btn.setStyleSheet(f"""
            QPushButton {{ background-color: #dc2626; color: white; {_btn_style} }}
            QPushButton:hover {{ background-color: #b91c1c; }}
        """)
        self._delete_btn.clicked.connect(self._on_roi_delete_clicked)
        self._delete_btn.setVisible(False)

        self._color_btn = QPushButton(self)
        self._color_btn.setFixedSize(40, 40)
        self._color_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._color_btn.setToolTip("Цвет области")
        self._color_btn.clicked.connect(self._pick_color)
        self._color_btn.setVisible(False)
        self._update_color_btn_style()

        self._first_fixation_cb = QCheckBox("Первая точка фиксации", self)
        self._first_fixation_cb.setFont(_font)
        self._first_fixation_cb.setStyleSheet("""
            QCheckBox { color: white; background: transparent; spacing: 8px; }
            QCheckBox::indicator { width: 18px; height: 18px; border-radius: 4px;
                border: 2px solid #4b5563; background: rgba(40,40,40,210); }
            QCheckBox::indicator:checked { background: #2563eb; border-color: #2563eb; }
            QCheckBox::indicator:hover { border-color: #9ca3af; }
        """)
        self._first_fixation_cb.setVisible(False)

    _CLOSE_HIT_RADIUS = 12

    def show_over_window(self) -> None:
        top = self.parent()
        while top.parent() is not None:
            top = top.parent()
        self.setParent(top)
        self.setGeometry(top.rect())
        self.raise_()
        self.show()
        self.setFocus()

    def _compute_img_rect(self) -> QRect:
        max_w = int(self.width() * 0.70)
        max_h = int(self.height() * 0.80)
        scaled = self._original_pm.scaled(
            max_w, max_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        return QRect(x, y, scaled.width(), scaled.height())

    def _screen_to_norm(self, pos: QPoint, img_rect: QRect) -> tuple[float, float]:
        x = max(0.0, min(1.0, (pos.x() - img_rect.x()) / img_rect.width()))
        y = max(0.0, min(1.0, (pos.y() - img_rect.y()) / img_rect.height()))
        return x, y

    def _norm_to_screen(self, nx: float, ny: float, img_rect: QRect) -> QPoint:
        return QPoint(
            img_rect.x() + int(nx * img_rect.width()),
            img_rect.y() + int(ny * img_rect.height()),
        )

    def _update_color_btn_style(self) -> None:
        c = self._current_color.name()
        self._color_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {c};
                border: 2px solid rgba(255,255,255,0.4);
                border-radius: 8px;
            }}
            QPushButton:hover {{
                border-color: white;
            }}
        """)

    def _pick_color(self) -> None:
        from PyQt6.QtWidgets import QColorDialog
        color = QColorDialog.getColor(self._current_color, self, "Цвет области")
        if color.isValid():
            self._current_color = color
            self._update_color_btn_style()
            self.update()

    def _update_button_visibility(self) -> None:
        in_viewing = self._mode == "viewing"
        in_roi_edit = self._mode == "roi_edit"
        self._add_btn.setVisible(in_viewing and self._roi_editing)
        self._name_input.setVisible(not in_viewing)
        self._color_btn.setVisible(not in_viewing)
        self._first_fixation_cb.setVisible(not in_viewing)
        self._save_btn.setVisible(not in_viewing)
        self._cancel_btn.setVisible(not in_viewing)
        self._delete_btn.setVisible(in_roi_edit)

    def _enter_drawing_mode(self) -> None:
        self._mode = "drawing"
        self._polygon_closed = False
        self._points.clear()
        self._name_input.clear()
        self._first_fixation_cb.setChecked(False)
        self._save_btn.setEnabled(False)
        self._update_button_visibility()
        self._reposition_buttons()
        self.update()

    def _cancel_drawing(self) -> None:
        self._mode = "viewing"
        self._polygon_closed = False
        self._points.clear()
        self._update_button_visibility()
        self._reposition_buttons()
        self.update()

    def _close_polygon(self) -> None:
        """Mark the polygon as closed; Save becomes active once a name is entered."""
        self._polygon_closed = True
        self._save_btn.setEnabled(bool(self._name_input.text().strip()))
        self.update()

    def _on_name_changed(self, text: str) -> None:
        if self._mode == "roi_edit":
            self._save_btn.setEnabled(bool(text.strip()))
        else:
            self._save_btn.setEnabled(self._polygon_closed and bool(text.strip()))

    def _on_cancel_clicked(self) -> None:
        if self._mode == "roi_edit":
            self._exit_roi_edit_mode()
        else:
            self._cancel_drawing()

    def _on_save_clicked(self) -> None:
        if self._mode == "roi_edit":
            self._save_roi_edit()
        else:
            self._save_new_roi()

    def _save_new_roi(self) -> None:
        roi = {
            "name": self._name_input.text().strip(),
            "color": self._current_color.name(),
            "first_fixation": self._first_fixation_cb.isChecked(),
            "points": [{"x": x, "y": y} for x, y in self._points],
        }
        self._existing_rois = self._existing_rois + [roi]
        self.roi_saved.emit(self._image_filename, list(self._existing_rois))
        self._current_color = QColor(0, 220, 100)
        self._update_color_btn_style()
        self._cancel_drawing()

    def _enter_roi_edit_mode(self, idx: int) -> None:
        self._selected_roi_idx = idx
        self._mode = "roi_edit"
        roi = self._existing_rois[idx]
        self._name_input.setText(roi.get("name", ""))
        self._current_color = QColor(roi["color"]) if roi.get("color") else QColor(0, 220, 100)
        self._update_color_btn_style()
        self._first_fixation_cb.setChecked(bool(roi.get("first_fixation", False)))
        self._save_btn.setEnabled(bool(self._name_input.text().strip()))
        self._update_button_visibility()
        self._reposition_buttons()
        self.update()

    def _exit_roi_edit_mode(self) -> None:
        self._selected_roi_idx = None
        self._mode = "viewing"
        self._current_color = QColor(0, 220, 100)
        self._update_color_btn_style()
        self._first_fixation_cb.setChecked(False)
        self._update_button_visibility()
        self._reposition_buttons()
        self.update()

    def _save_roi_edit(self) -> None:
        if self._selected_roi_idx is None:
            return
        roi = dict(self._existing_rois[self._selected_roi_idx])
        roi["name"] = self._name_input.text().strip()
        roi["color"] = self._current_color.name()
        roi["first_fixation"] = self._first_fixation_cb.isChecked()
        rois = list(self._existing_rois)
        rois[self._selected_roi_idx] = roi
        self._existing_rois = rois
        self.roi_saved.emit(self._image_filename, list(self._existing_rois))
        self._exit_roi_edit_mode()

    def _on_roi_delete_clicked(self) -> None:
        if self._selected_roi_idx is None:
            return
        rois = list(self._existing_rois)
        rois.pop(self._selected_roi_idx)
        self._existing_rois = rois
        self.roi_saved.emit(self._image_filename, list(self._existing_rois))
        self._exit_roi_edit_mode()

    def _reposition_buttons(self) -> None:
        self._close_btn.move(self.width() - 50, 14)
        btn_h = 40
        cb_h = 28
        gap_rows = 10
        bottom_y = self.height() - btn_h - 24
        if self._mode != "viewing":
            cb_y = bottom_y - cb_h - gap_rows
            self._first_fixation_cb.adjustSize()
            cb_w = self._first_fixation_cb.sizeHint().width()
            self._first_fixation_cb.setGeometry((self.width() - cb_w) // 2, cb_y, cb_w, cb_h)
        if self._mode == "viewing":
            self._add_btn.adjustSize()
            btn_w = max(self._add_btn.sizeHint().width() + 20, 240)
            self._add_btn.setGeometry((self.width() - btn_w) // 2, bottom_y, btn_w, btn_h)
        else:
            color_w = btn_h  # square
            input_w = 220
            save_w = 110
            cancel_w = 100
            delete_w = 100
            gap = 8
            in_roi_edit = self._mode == "roi_edit"
            total = color_w + gap + input_w + gap + save_w + gap + cancel_w
            if in_roi_edit:
                total += gap + delete_w
            x = (self.width() - total) // 2
            self._color_btn.setGeometry(x, bottom_y, color_w, btn_h)
            self._name_input.setGeometry(x + color_w + gap, bottom_y, input_w, btn_h)
            self._save_btn.setGeometry(x + color_w + gap + input_w + gap, bottom_y, save_w, btn_h)
            self._cancel_btn.setGeometry(x + color_w + gap + input_w + gap + save_w + gap, bottom_y, cancel_w, btn_h)
            if in_roi_edit:
                self._delete_btn.setGeometry(x + color_w + gap + input_w + gap + save_w + gap + cancel_w + gap, bottom_y, delete_w, btn_h)

    def _draw_existing_rois(self, painter: QPainter, img_rect: QRect) -> None:
        for i, roi in enumerate(self._existing_rois):
            if len(roi.get("points", [])) < 2:
                continue
            pts = [self._norm_to_screen(p["x"], p["y"], img_rect) for p in roi["points"]]
            poly = QPolygon(pts)
            base = QColor(roi["color"]) if roi.get("color") else QColor(0, 220, 100)
            selected = i == self._selected_roi_idx
            fill = QColor(base.red(), base.green(), base.blue(), 100 if selected else 60)
            painter.setBrush(fill)
            painter.setPen(QPen(base, 3 if selected else 2))
            painter.drawPolygon(poly)
            cx = int(sum(p.x() for p in pts) / len(pts))
            cy = int(sum(p.y() for p in pts) / len(pts))
            label = roi.get("name", "")
            first_fixation = roi.get("first_fixation", False)
            fm = painter.fontMetrics()
            tw = fm.horizontalAdvance(label)
            th = fm.height()
            pad = 4
            box_s = th - 2  # side length of the [1] square
            box_gap = 6
            content_w = (box_s + box_gap + tw) if first_fixation else tw
            bg_x = cx - content_w // 2 - pad
            bg_y = cy - th // 2 - pad
            painter.setBrush(QColor(0, 0, 0, 160))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(bg_x, bg_y, content_w + pad * 2, th + pad * 2, 4, 4)
            text_x = cx - content_w // 2
            if first_fixation:
                box_x = text_x
                box_y = cy - box_s // 2
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(QColor(255, 255, 255, 200), 1))
                painter.drawRoundedRect(box_x, box_y, box_s, box_s, 2, 2)
                painter.setPen(QColor(255, 255, 255))
                painter.drawText(QRect(box_x, box_y, box_s, box_s), Qt.AlignmentFlag.AlignCenter, "1")
                text_x += box_s + box_gap
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(text_x, cy + th // 2 - 2, label)

    def _draw_in_progress(self, painter: QPainter, img_rect: QRect) -> None:
        if not self._points:
            return
        screen_pts = [self._norm_to_screen(x, y, img_rect) for x, y in self._points]
        c = self._current_color
        if self._polygon_closed:
            # Draw as a filled closed polygon using the selected color
            poly = QPolygon(screen_pts)
            painter.setBrush(QColor(c.red(), c.green(), c.blue(), 40))
            painter.setPen(QPen(c, 2))
            painter.drawPolygon(poly)
            return
        # Open polygon: draw lines between consecutive points
        painter.setPen(QPen(QColor(255, 255, 255), 2))
        for i in range(1, len(screen_pts)):
            painter.drawLine(screen_pts[i - 1], screen_pts[i])
        # Draw points
        for i, pt in enumerate(screen_pts):
            if i == 0:
                near_first = (
                    len(self._points) >= 3
                    and self._cursor_pos is not None
                    and (
                        (self._cursor_pos.x() - pt.x()) ** 2
                        + (self._cursor_pos.y() - pt.y()) ** 2
                    ) ** 0.5 <= self._CLOSE_HIT_RADIUS
                )
                if near_first:
                    painter.setPen(QPen(QColor(255, 220, 0), 2))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawEllipse(pt, 14, 14)
                painter.setBrush(QColor(255, 220, 0))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(pt, 9, 9)
            else:
                painter.setBrush(QColor(255, 255, 255))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(pt, 5, 5)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        painter.setOpacity(0.85)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        painter.setOpacity(1.0)

        img_rect = self._compute_img_rect()
        scaled = self._original_pm.scaled(
            img_rect.width(), img_rect.height(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        painter.drawPixmap(img_rect.x(), img_rect.y(), scaled)

        self._draw_existing_rois(painter, img_rect)
        if self._mode == "drawing":
            self._draw_in_progress(painter, img_rect)

        painter.end()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._reposition_buttons()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        from PyQt6.QtCore import QEvent
        if obj is self._name_input and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                self._on_cancel_clicked()
                return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            if self._mode == "drawing":
                self._cancel_drawing()
            elif self._mode == "roi_edit":
                self._exit_roi_edit_mode()
            else:
                self.close()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self._mode == "drawing":
            if event.button() == Qt.MouseButton.LeftButton and not self._polygon_closed:
                img_rect = self._compute_img_rect()
                if img_rect.contains(event.pos()):
                    x_norm, y_norm = self._screen_to_norm(event.pos(), img_rect)
                    self._points.append((x_norm, y_norm))
                    self.update()
            return
        if self._mode == "roi_edit":
            if not self._compute_img_rect().contains(event.pos()):
                self._exit_roi_edit_mode()
            return
        # viewing mode
        img_rect = self._compute_img_rect()
        if not img_rect.contains(event.pos()):
            self.close()
            return
        if self._roi_editing and event.button() == Qt.MouseButton.LeftButton:
            for i, roi in enumerate(self._existing_rois):
                pts = [self._norm_to_screen(p["x"], p["y"], img_rect) for p in roi.get("points", [])]
                if len(pts) >= 3 and QPolygon(pts).containsPoint(event.pos(), Qt.FillRule.OddEvenFill):
                    self._enter_roi_edit_mode(i)
                    return

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if self._mode != "drawing" or event.button() != Qt.MouseButton.LeftButton:
            return
        if self._polygon_closed or len(self._points) < 3:
            return
        img_rect = self._compute_img_rect()
        first_pt = self._norm_to_screen(self._points[0][0], self._points[0][1], img_rect)
        dist = ((event.pos().x() - first_pt.x()) ** 2 + (event.pos().y() - first_pt.y()) ** 2) ** 0.5
        if dist <= self._CLOSE_HIT_RADIUS:
            if self._points:
                self._points.pop()  # remove duplicate from preceding mousePressEvent
            self._close_polygon()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        self._cursor_pos = event.pos()
        if self._mode == "drawing":
            self.update()
        super().mouseMoveEvent(event)


class _DraggableTile(QWidget):
    """Image tile that supports click-to-preview and drag-to-reorder."""

    preview_requested = pyqtSignal(str)

    def __init__(
        self,
        path: str,
        pixmap: QPixmap | None,
        draggable: bool,
        rois: list[dict] | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._path = path
        self._pixmap = pixmap
        self._draggable = draggable
        self._rois: list[dict] = rois or []
        self._highlighted = False
        self._drag_start: QPoint | None = None
        self.setFixedSize(TILE_W, TILE_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_highlight(self, on: bool) -> None:
        self._highlighted = on
        self.update()

    def set_rois(self, rois: list[dict]) -> None:
        self._rois = rois
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background
        painter.setBrush(QColor(BG_SIDEBAR))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.rect(), CORNER_RADIUS, CORNER_RADIUS)

        # Image centred inside the tile
        if self._pixmap:
            x = (self.width() - self._pixmap.width()) // 2
            y = (self.height() - self._pixmap.height()) // 2
            painter.drawPixmap(x, y, self._pixmap)

        # Highlight border
        if self._highlighted:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(BG_SIDEBAR_ACTIVE), 2))
            painter.drawRoundedRect(1, 1, self.width() - 2, self.height() - 2, CORNER_RADIUS, CORNER_RADIUS)

        # ROI badges
        if self._rois:
            self._paint_badges(painter)

        painter.end()

    def _paint_badges(self, painter: QPainter) -> None:
        badge_h = 22
        badge_gap = 4
        margin_x = 6
        margin_y = 6
        pad_x = 8
        box_s = 14  # size of the "1" square

        font = QFont(FONT_FAMILY, 9)
        painter.setFont(font)
        fm = painter.fontMetrics()

        y = self.height() - margin_y - badge_h
        x = margin_x
        for roi in self._rois:
            name = roi.get("name", "")
            first_fixation = roi.get("first_fixation", False)
            base = QColor(roi["color"]) if roi.get("color") else QColor(0, 220, 100)
            text_w = fm.horizontalAdvance(name)

            if first_fixation:
                badge_w = pad_x + box_s + 6 + text_w + pad_x
            else:
                badge_w = pad_x + text_w + pad_x

            if x + badge_w > self.width() - margin_x:
                break

            pill = QRect(x, y, badge_w, badge_h)
            painter.setBrush(QColor(base.red(), base.green(), base.blue(), 200))
            painter.setPen(QPen(base.darker(130), 1))
            painter.drawRoundedRect(pill, badge_h / 2, badge_h / 2)

            painter.setPen(QColor(255, 255, 255))
            if first_fixation:
                box_x = x + (badge_h - box_s) // 2
                box_y = y + (badge_h - box_s) // 2
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(QColor(255, 255, 255, 200), 1))
                painter.drawRoundedRect(box_x, box_y, box_s, box_s, 3, 3)
                painter.setPen(QColor(255, 255, 255))
                painter.drawText(QRect(box_x, box_y, box_s, box_s), Qt.AlignmentFlag.AlignCenter, "1")
                text_rect = QRect(box_x + box_s + 6, y, badge_w - (box_x - x + box_s + 6 + pad_x), badge_h)
                painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, name)
            else:
                painter.drawText(pill, Qt.AlignmentFlag.AlignCenter, name)

            x += badge_w + badge_gap

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
            self._drag_start = None
            self.preview_requested.emit(self._path)


class ImageGridWidget(QWidget):
    """Tile grid showing a '+' add-button followed by 16:9 image thumbnails."""

    add_clicked = pyqtSignal()
    images_changed = pyqtSignal()
    roi_saved = pyqtSignal(str, list)

    def __init__(self, parent: QWidget | None = None, readonly: bool = False):
        super().__init__(parent)
        self._paths: list[str] = []
        self._pixmaps: dict[str, QPixmap] = {}
        self._cols = 1
        self._readonly = readonly
        self._drop_target_index: int | None = None
        self._tiles: list[_DraggableTile] = []
        self._regions: dict[str, list[dict]] = {}

        self.setAcceptDrops(True)

        self._grid_layout = QGridLayout(self)
        self._grid_layout.setSpacing(TILE_GAP)
        self._grid_layout.setContentsMargins(0, 0, 0, 0)

        self._rebuild_grid()

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

    def set_regions(self, regions: dict[str, list[dict]]) -> None:
        self._regions = dict(regions)

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

        self._paths.pop(source_idx)
        self._paths.insert(target_idx, source_path)
        self._rebuild_grid()
        self.images_changed.emit()
        event.acceptProposedAction()

    def resizeEvent(self, event):  # noqa: N802
        new_cols = max(1, (self.width() - TILE_GAP) // (TILE_W + TILE_GAP))
        if new_cols != self._cols:
            self._cols = new_cols
            self._rebuild_grid()
        super().resizeEvent(event)

    def _on_preview_requested(self, path: str) -> None:
        pm = QPixmap(path)
        if pm.isNull():
            return
        filename = Path(path).name
        existing_rois = self._regions.get(filename, [])
        overlay = ImagePreviewOverlay(
            pm,
            roi_editing=not self._readonly,
            existing_rois=existing_rois,
            image_filename=filename,
            parent=self,
        )
        overlay.roi_saved.connect(self._on_overlay_roi_saved)
        overlay.show_over_window()

    def _on_overlay_roi_saved(self, filename: str, rois: list) -> None:
        self._regions[filename] = rois
        self.roi_saved.emit(filename, rois)
        for i, path in enumerate(self._paths):
            if Path(path).name == filename and i < len(self._tiles):
                self._tiles[i].set_rois(rois)
                break

    def _index_at_pos(self, pos: QPoint) -> int | None:
        """Return the image index (into self._paths) at the given widget position."""
        for i, tile in enumerate(self._tiles):
            tile_pos = tile.parent().mapTo(self, QPoint(0, 0)) if tile.parent() != self else tile.pos()
            tile_rect = tile.rect().translated(tile_pos)
            if tile_rect.contains(pos):
                return i
        if self._tiles and pos.y() >= 0:
            return len(self._tiles) - 1
        return None

    def _clear_highlight(self) -> None:
        for tile in self._tiles:
            tile.set_highlight(False)

    def _remove_image(self, path: str) -> None:
        self.remove_image(path)

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
            rois = self._regions.get(Path(path).name, [])
            tile = _DraggableTile(path, pm, draggable=draggable, rois=rois, parent=container)
            tile.preview_requested.connect(self._on_preview_requested)
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
