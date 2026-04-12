"""Unified form page for creating, viewing, and editing a test."""

from __future__ import annotations

import logging
from enum import Enum, auto
from pathlib import Path

from PyQt6.QtCore import QPoint, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QPixmap, QPolygon
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from eyetracker.data.test import TestDao, TestData
from eyetracker.ui.theme import (
    BG_MAIN,
    BG_SIDEBAR,
    BORDER_COLOR,
    BUTTON_BG,
    BUTTON_HOVER,
    CORNER_RADIUS,
    ERROR_COLOR,
    FONT_FAMILY,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

logger = logging.getLogger(__name__)

_IMAGE_FILTER = "Изображения (*.png *.jpg *.jpeg *.bmp *.gif *.webp)"


class FormMode(Enum):
    CREATE = auto()
    VIEW = auto()
    EDIT = auto()


def pick_image(parent: QWidget) -> str | None:
    """Open a file-picker for images. Returns path or None."""
    path, _ = QFileDialog.getOpenFileName(parent, "Выберите изображение", "", _IMAGE_FILTER)
    if not path:
        return None
    if QPixmap(path).isNull():
        QMessageBox.warning(parent, "Ошибка", "Не удалось загрузить изображение")
        return None
    return path


_CLOSE_HIT_RADIUS = 12


class AoiCanvas(QWidget):
    """Interactive canvas for displaying an image and drawing AOI polygons on it."""

    aoi_changed = pyqtSignal(list)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._pixmap: QPixmap | None = None
        self._aois: list[dict] = []
        self._drawing = False
        self._points: list[tuple[float, float]] = []
        self._cursor_pos: QPoint | None = None
        self._draw_color = QColor(0, 220, 100)
        self._hovering_first = False
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def set_image(self, pm: QPixmap, aois: list[dict] | None = None) -> None:
        self._pixmap = pm
        self._aois = list(aois) if aois else []
        self.setFixedSize(pm.size())
        self.update()

    def set_draw_color(self, color: QColor) -> None:
        self._draw_color = color
        self.update()

    def start_drawing(self) -> None:
        self._drawing = True
        self._points.clear()
        self._draw_color = QColor(0, 220, 100)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.update()

    def cancel_drawing(self) -> None:
        self._drawing = False
        self._points.clear()
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.update()

    def is_drawing(self) -> bool:
        return self._drawing

    def remove_aoi(self, idx: int) -> None:
        if 0 <= idx < len(self._aois):
            self._aois.pop(idx)
            self.update()
            self.aoi_changed.emit(self._aois)

    def add_aoi(self, aoi: dict) -> None:
        self._aois.append(aoi)
        self.update()
        self.aoi_changed.emit(self._aois)

    def get_aois(self) -> list[dict]:
        return list(self._aois)

    @staticmethod
    def _is_convex(points: list[tuple[float, float]]) -> bool:
        n = len(points)
        if n < 3:
            return False
        sign = 0
        for i in range(n):
            ax, ay = points[i]
            bx, by = points[(i + 1) % n]
            cx, cy = points[(i + 2) % n]
            cross = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
            if cross != 0:
                if sign == 0:
                    sign = 1 if cross > 0 else -1
                elif (cross > 0) != (sign > 0):
                    return False
        return True

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if not self._drawing or self._pixmap is None:
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position()
        w, h = self._pixmap.width(), self._pixmap.height()
        nx, ny = pos.x() / w, pos.y() / h
        self._points.append((nx, ny))
        self.update()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if not self._drawing or self._pixmap is None:
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if len(self._points) >= 3:
            # Remove the extra point added by the preceding mousePressEvent
            self._points.pop()
            self._close_polygon()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drawing and self._pixmap is not None:
            self._cursor_pos = event.position().toPoint()
            # Detect hover over first point
            old = self._hovering_first
            self._hovering_first = False
            if len(self._points) >= 3:
                w, h = self._pixmap.width(), self._pixmap.height()
                fx, fy = self._points[0]
                dist = ((self._cursor_pos.x() - fx * w) ** 2 + (self._cursor_pos.y() - fy * h) ** 2) ** 0.5
                self._hovering_first = dist < _CLOSE_HIT_RADIUS * 1.5
            if old != self._hovering_first or self._drawing:
                self.update()

    def _close_polygon(self) -> None:
        if not self._is_convex(self._points):
            QMessageBox.warning(
                self,
                "Невыпуклый многоугольник",
                "Зона интереса должна быть выпуклым многоугольником.\n"
                "Пожалуйста, нарисуйте область заново.",
            )
            self._points.clear()
            self.update()
            return
        self._drawing = False
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.update()

    def get_pending_points(self) -> list[tuple[float, float]]:
        if not self._drawing and self._points:
            return list(self._points)
        return []

    def clear_pending(self) -> None:
        self._points.clear()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        if self._pixmap is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.drawPixmap(0, 0, self._pixmap)
        w, h = self._pixmap.width(), self._pixmap.height()

        # Draw existing AOIs
        for roi in self._aois:
            points = roi.get("points", [])
            if len(points) < 2:
                continue
            pts = [QPoint(int(pt["x"] * w), int(pt["y"] * h)) for pt in points]
            poly = QPolygon(pts)
            base = QColor(roi["color"]) if roi.get("color") else QColor(0, 220, 100)
            fill = QColor(base.red(), base.green(), base.blue(), 60)
            p.setBrush(fill)
            p.setPen(QPen(base, 2))
            p.drawPolygon(poly)
            # Label
            cx = int(sum(pt.x() for pt in pts) / len(pts))
            cy = int(sum(pt.y() for pt in pts) / len(pts))
            label = roi.get("name", "")
            if not label:
                continue
            first_fixation = roi.get("first_fixation", False)
            fm = p.fontMetrics()
            tw = fm.horizontalAdvance(label)
            th = fm.height()
            pad = 4
            box_s = th - 2
            box_gap = 6
            content_w = (box_s + box_gap + tw) if first_fixation else tw
            bg_x = cx - content_w // 2 - pad
            bg_y = cy - th // 2 - pad
            p.setBrush(QColor(0, 0, 0, 160))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(bg_x, bg_y, content_w + pad * 2, th + pad * 2, 4, 4)
            text_x = cx - content_w // 2
            if first_fixation:
                box_x = text_x
                box_y = cy - box_s // 2
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(QColor(255, 255, 255, 200), 1))
                p.drawRoundedRect(box_x, box_y, box_s, box_s, 2, 2)
                p.setPen(QColor(255, 255, 255))
                p.drawText(QRect(box_x, box_y, box_s, box_s), Qt.AlignmentFlag.AlignCenter, "1")
                text_x += box_s + box_gap
            p.setPen(QColor(255, 255, 255))
            p.drawText(text_x, cy + th // 2 - 2, label)

        # Draw in-progress polygon
        if self._points:
            pts_px = [QPoint(int(x * w), int(y * h)) for x, y in self._points]
            color = QColor(self._draw_color)
            p.setPen(QPen(color, 2, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            for i in range(len(pts_px) - 1):
                p.drawLine(pts_px[i], pts_px[i + 1])
            # Line to cursor
            if self._drawing and self._cursor_pos is not None and pts_px:
                faded = QColor(color.red(), color.green(), color.blue(), 120)
                p.setPen(QPen(faded, 1, Qt.PenStyle.DotLine))
                p.drawLine(pts_px[-1], self._cursor_pos)
            # Vertices
            for i, pt in enumerate(pts_px):
                if i == 0:
                    # First point — larger, with hover glow
                    radius = 10 if self._hovering_first else 8
                    if self._hovering_first:
                        glow = QColor(255, 255, 255, 80)
                        p.setPen(Qt.PenStyle.NoPen)
                        p.setBrush(glow)
                        p.drawEllipse(pt, radius + 4, radius + 4)
                    p.setPen(QPen(QColor(255, 255, 255), 2))
                    p.setBrush(color)
                    p.drawEllipse(pt, radius, radius)
                else:
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(color)
                    p.drawEllipse(pt, 4, 4)
            # If polygon closed (not drawing), show filled
            if not self._drawing and len(pts_px) >= 3:
                fill = QColor(color.red(), color.green(), color.blue(), 50)
                p.setBrush(fill)
                p.setPen(QPen(color, 2))
                p.drawPolygon(QPolygon(pts_px))

        p.end()


class TestFormPage(QWidget):
    """Form for creating / viewing / editing a test."""

    back_requested = pyqtSignal()
    test_created = pyqtSignal(str)  # carries new test_id
    test_updated = pyqtSignal()
    test_deleted = pyqtSignal()
    edit_requested = pyqtSignal()
    run_test_requested = pyqtSignal()
    results_requested = pyqtSignal()

    def __init__(
        self,
        dao: TestDao,
        mode: FormMode = FormMode.CREATE,
        test_data: TestData | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._dao = dao
        self._mode = mode
        self._test_data = test_data
        self._image_path: str | None = None
        self._original_name: str | None = None
        self.setStyleSheet(f"background-color: {BG_MAIN};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # -- top bar ---------------------------------------------------------
        root.addWidget(self._build_top_bar())

        # -- scrollable body -------------------------------------------------
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(40, 30, 40, 30)
        body_layout.setSpacing(0)

        self._build_name_section(body_layout)
        body_layout.addSpacing(24)
        self._build_image_section(body_layout)
        body_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        root.addWidget(scroll)

        # -- populate data for view/edit -------------------------------------
        if test_data is not None and mode in (FormMode.VIEW, FormMode.EDIT):
            self._populate(test_data)

    # -- top bar -------------------------------------------------------------

    def _build_top_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(52)
        bar.setStyleSheet(f"background-color: {BG_MAIN}; border-bottom: 1px solid {BORDER_COLOR};")

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 16, 0)

        back_btn = QPushButton("← Назад")
        back_btn.setFont(QFont(FONT_FAMILY, 13))
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.setStyleSheet(f"""
            QPushButton {{
                color: {BUTTON_BG};
                background: transparent;
                border: none;
                padding: 6px 12px;
            }}
            QPushButton:hover {{ color: {BUTTON_HOVER}; }}
        """)
        back_btn.clicked.connect(self.back_requested.emit)

        titles = {
            FormMode.CREATE: "Создание теста",
            FormMode.VIEW: "Просмотр теста",
            FormMode.EDIT: "Редактирование теста",
        }
        title = QLabel(titles[self._mode])
        title.setFont(QFont(FONT_FAMILY, 16, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(back_btn)
        layout.addStretch()
        layout.addWidget(title)
        layout.addStretch()

        if self._mode == FormMode.CREATE:
            layout.addWidget(self._make_action_button("Создать", self._on_create_clicked))
        elif self._mode == FormMode.VIEW:
            self._build_view_actions(layout)

        return bar

    def _make_action_button(self, text: str, handler) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedSize(120, 34)
        btn.setFont(QFont(FONT_FAMILY, 13, QFont.Weight.Bold))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
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
        btn.clicked.connect(handler)
        return btn

    def _build_view_actions(self, layout: QHBoxLayout) -> None:
        actions = [
            ("Скопировать код", self._on_copy_code_clicked),
            ("Пройти", self._on_use_clicked),
            ("Результаты", self._on_results_clicked),
            ("Выгрузить Json", self._on_export_clicked),
            ("Удалить", self._on_delete_clicked),
        ]
        for text, handler in actions:
            btn = QPushButton(text)
            btn.setFixedHeight(34)
            btn.setFont(QFont(FONT_FAMILY, 12))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if text == "Удалить":
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: transparent;
                        color: {ERROR_COLOR};
                        border: 1px solid {ERROR_COLOR};
                        border-radius: {CORNER_RADIUS}px;
                        padding: 0 14px;
                    }}
                    QPushButton:hover {{
                        background-color: {ERROR_COLOR};
                        color: white;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: transparent;
                        color: {BUTTON_BG};
                        border: 1px solid {BUTTON_BG};
                        border-radius: {CORNER_RADIUS}px;
                        padding: 0 14px;
                    }}
                    QPushButton:hover {{
                        background-color: {BUTTON_BG};
                        color: white;
                    }}
                """)
            btn.clicked.connect(handler)
            layout.addWidget(btn)

    # -- name section --------------------------------------------------------

    def _build_name_section(self, parent_layout: QVBoxLayout) -> None:
        label = QLabel("Название")
        label.setFont(QFont(FONT_FAMILY, 14, QFont.Weight.Bold))
        label.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Введите название теста")
        self._name_edit.setFont(QFont(FONT_FAMILY, 14))
        self._name_edit.setFixedHeight(40)
        self._name_edit.setStyleSheet(f"""
            QLineEdit {{
                background-color: {BG_SIDEBAR};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER_COLOR};
                border-radius: {CORNER_RADIUS}px;
                padding: 0 12px;
            }}
            QLineEdit:focus {{
                border-color: {BUTTON_BG};
            }}
        """)

        if self._mode == FormMode.VIEW:
            self._name_edit.setReadOnly(True)

        self._name_error = self._make_error_label()

        parent_layout.addWidget(label)
        parent_layout.addSpacing(6)
        if self._mode == FormMode.VIEW:
            name_row = QHBoxLayout()
            name_row.setSpacing(6)
            name_row.addWidget(self._name_edit)
            edit_btn = QPushButton("\u270E")
            edit_btn.setFixedSize(40, 40)
            edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            edit_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {TEXT_SECONDARY};
                    border: 1px solid {BORDER_COLOR};
                    border-radius: {CORNER_RADIUS}px;
                    font-size: 18px;
                }}
                QPushButton:hover {{
                    color: {TEXT_PRIMARY};
                    border-color: {BUTTON_BG};
                }}
            """)
            edit_btn.clicked.connect(self._on_edit_clicked)
            name_row.addWidget(edit_btn)
            parent_layout.addLayout(name_row)
        elif self._mode == FormMode.EDIT:
            name_row = QHBoxLayout()
            name_row.setSpacing(6)
            name_row.addWidget(self._name_edit)
            save_btn = QPushButton("\u2713")
            save_btn.setFixedSize(40, 40)
            save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            save_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {BUTTON_BG};
                    color: white;
                    border: none;
                    border-radius: {CORNER_RADIUS}px;
                    font-size: 20px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: {BUTTON_HOVER};
                }}
            """)
            save_btn.clicked.connect(self._on_save_clicked)
            name_row.addWidget(save_btn)
            parent_layout.addLayout(name_row)
        else:
            parent_layout.addWidget(self._name_edit)
        parent_layout.addSpacing(4)
        parent_layout.addWidget(self._name_error)

    # -- image section -------------------------------------------------------

    def _build_image_section(self, parent_layout: QVBoxLayout) -> None:
        label = QLabel("Изображение")
        label.setFont(QFont(FONT_FAMILY, 14, QFont.Weight.Bold))
        label.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")

        self._image_label = QLabel()
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setStyleSheet(f"""
            QLabel {{
                background-color: {BG_SIDEBAR};
                border: 2px dashed {BORDER_COLOR};
                border-radius: {CORNER_RADIUS}px;
                color: {TEXT_SECONDARY};
            }}
        """)

        # AOI canvas (used in VIEW mode instead of QLabel)
        self._aoi_canvas = AoiCanvas()
        self._aoi_canvas.setVisible(False)

        if self._mode == FormMode.CREATE:
            self._image_label.setFixedSize(300, 300)
            self._image_label.setText("Нет изображения\n\nНажмите для выбора")
            self._image_label.setFont(QFont(FONT_FAMILY, 12))
            self._image_label.setCursor(Qt.CursorShape.PointingHandCursor)
            self._image_label.mousePressEvent = lambda _: self._on_choose_image()

        self._image_error = self._make_error_label()

        parent_layout.addWidget(label)
        parent_layout.addSpacing(6)
        parent_layout.addWidget(self._image_label, alignment=Qt.AlignmentFlag.AlignHCenter)
        parent_layout.addWidget(self._aoi_canvas, alignment=Qt.AlignmentFlag.AlignHCenter)
        parent_layout.addSpacing(4)
        parent_layout.addWidget(self._image_error)

        # AOI panel (VIEW mode only) — always visible
        if self._mode == FormMode.VIEW:
            parent_layout.addSpacing(12)
            self._build_aoi_section(parent_layout)

    def _build_aoi_section(self, parent_layout: QVBoxLayout) -> None:
        _btn_style = f"""
            QPushButton {{
                background-color: transparent;
                color: {BUTTON_BG};
                border: 1px solid {BUTTON_BG};
                border-radius: {CORNER_RADIUS}px;
                padding: 8px 20px;
            }}
            QPushButton:hover {{
                background-color: {BUTTON_BG};
                color: white;
            }}
        """

        # AOI list container
        self._aoi_list_container = QVBoxLayout()
        self._aoi_list_container.setSpacing(4)
        parent_layout.addLayout(self._aoi_list_container)

        # New AOI form (hidden until polygon is closed)
        self._aoi_form = QWidget()
        self._aoi_form.setVisible(False)
        form_layout = QVBoxLayout(self._aoi_form)
        form_layout.setContentsMargins(0, 8, 0, 0)
        form_layout.setSpacing(6)

        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        self._aoi_name_input = QLineEdit()
        self._aoi_name_input.setPlaceholderText("Название области")
        self._aoi_name_input.setFont(QFont(FONT_FAMILY, 13))
        self._aoi_name_input.setFixedHeight(34)
        self._aoi_name_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {BG_SIDEBAR};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER_COLOR};
                border-radius: {CORNER_RADIUS}px;
                padding: 0 10px;
            }}
            QLineEdit:focus {{ border-color: {BUTTON_BG}; }}
        """)
        name_row.addWidget(self._aoi_name_input)

        self._aoi_color_btn = QPushButton()
        self._aoi_color_btn.setFixedSize(34, 34)
        self._aoi_color_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._aoi_current_color = QColor(0, 220, 100)
        self._update_color_btn()
        self._aoi_color_btn.clicked.connect(self._on_aoi_pick_color)
        name_row.addWidget(self._aoi_color_btn)
        form_layout.addLayout(name_row)

        opts_row = QHBoxLayout()
        opts_row.setSpacing(12)
        self._aoi_first_fix_cb = QCheckBox("Первая фиксация")
        self._aoi_first_fix_cb.setFont(QFont(FONT_FAMILY, 12))
        self._aoi_first_fix_cb.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")
        opts_row.addWidget(self._aoi_first_fix_cb)
        opts_row.addStretch()

        save_aoi_btn = QPushButton("Сохранить область")
        save_aoi_btn.setFont(QFont(FONT_FAMILY, 12))
        save_aoi_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_aoi_btn.setFixedHeight(32)
        save_aoi_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {BUTTON_BG}; color: white;
                border: none; border-radius: {CORNER_RADIUS}px; padding: 0 16px;
            }}
            QPushButton:hover {{ background-color: {BUTTON_HOVER}; }}
        """)
        save_aoi_btn.clicked.connect(self._on_aoi_save_region)
        opts_row.addWidget(save_aoi_btn)

        cancel_aoi_btn = QPushButton("Отмена")
        cancel_aoi_btn.setFont(QFont(FONT_FAMILY, 12))
        cancel_aoi_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_aoi_btn.setFixedHeight(32)
        cancel_aoi_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent; color: {TEXT_SECONDARY};
                border: 1px solid {BORDER_COLOR}; border-radius: {CORNER_RADIUS}px; padding: 0 16px;
            }}
            QPushButton:hover {{ color: {TEXT_PRIMARY}; border-color: {TEXT_SECONDARY}; }}
        """)
        cancel_aoi_btn.clicked.connect(self._on_aoi_cancel_drawing)
        opts_row.addWidget(cancel_aoi_btn)
        form_layout.addLayout(opts_row)
        parent_layout.addWidget(self._aoi_form)

        # Add button
        self._aoi_add_btn = QPushButton("Добавить область")
        self._aoi_add_btn.setFont(QFont(FONT_FAMILY, 12))
        self._aoi_add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._aoi_add_btn.setStyleSheet(_btn_style)
        self._aoi_add_btn.clicked.connect(self._on_aoi_start_drawing)
        parent_layout.addWidget(self._aoi_add_btn, alignment=Qt.AlignmentFlag.AlignLeft)

    # -- populate from existing test -----------------------------------------

    def _populate(self, test: TestData) -> None:
        self._name_edit.setText(test.name)
        self._original_name = test.name
        image_path = str(self._dao.get_image_path(test))
        self._set_image_display(image_path, aoi=test.aoi)
        if self._mode == FormMode.VIEW:
            self._rebuild_aoi_list()

    def _set_image_display(self, path: str, *, aoi: list[dict] | None = None) -> None:
        self._image_path = path
        pm = QPixmap(path).scaled(
            960, 540,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        if self._mode == FormMode.VIEW:
            self._image_label.setVisible(False)
            self._aoi_canvas.setVisible(True)
            self._aoi_canvas.set_image(pm, aoi)
        else:
            self._image_label.setText("")
            self._image_label.setPixmap(pm)
            self._image_label.setFixedSize(pm.size())
            self._image_label.setStyleSheet(f"""
                QLabel {{
                    background-color: {BG_SIDEBAR};
                    border: 1px solid {BORDER_COLOR};
                    border-radius: {CORNER_RADIUS}px;
                }}
            """)

    # -- actions -------------------------------------------------------------

    def _on_choose_image(self) -> None:
        path = pick_image(self)
        if path is None:
            return
        self._set_image_display(path)
        self._image_error.setVisible(False)

    def _on_create_clicked(self) -> None:
        errors: dict[str, str] = {}
        if not self._name_edit.text().strip():
            errors["name"] = "Название не может быть пустым"
        if self._image_path is None:
            errors["image"] = "Выберите изображение"
        self._show_errors(errors)
        if errors:
            return

        try:
            test = self._dao.create(
                name=self._name_edit.text().strip(),
                image_src=Path(self._image_path),  # type: ignore[arg-type]
            )
            self.test_created.emit(test.id)
        except Exception as exc:
            logger.error("Failed to create test: %s", exc)
            QMessageBox.warning(self, "Ошибка", f"Не удалось сохранить тест: {exc}")

    def _on_save_clicked(self) -> None:
        errors: dict[str, str] = {}
        if not self._name_edit.text().strip():
            errors["name"] = "Название не может быть пустым"
        self._show_errors(errors)
        if errors:
            return
        if self._test_data is None:
            return
        new_name = self._name_edit.text().strip()
        try:
            if new_name != self._original_name:
                self._test_data = self._dao.update_name(self._test_data.id, new_name)
                self._original_name = new_name
        except Exception as exc:
            logger.error("Failed to update test: %s", exc)
            QMessageBox.warning(self, "Ошибка", f"Не удалось сохранить тест: {exc}")
            return
        self.test_updated.emit()

    def _on_edit_clicked(self) -> None:
        self.edit_requested.emit()

    def _on_copy_code_clicked(self) -> None:
        if self._test_data is None:
            return
        try:
            code = self._dao.get_token(self._test_data.id)
        except Exception as exc:
            QMessageBox.warning(self, "Ошибка", f"Не удалось получить код: {exc}")
            return
        QApplication.clipboard().setText(code)
        QMessageBox.information(self, "Код скопирован", f"Код теста {code} скопирован в буфер обмена")

    def _on_use_clicked(self) -> None:
        self.run_test_requested.emit()

    def _on_results_clicked(self) -> None:
        self.results_requested.emit()

    def _on_export_clicked(self) -> None:
        if self._test_data is None:
            return
        default_name = f"{self._test_data.name}.zip"
        path, _ = QFileDialog.getSaveFileName(
            self, "Экспорт теста", default_name, "ZIP архив (*.zip)"
        )
        if not path:
            return
        try:
            from eyetracker.data.test.export import export_test_zip
            export_test_zip(self._test_data, self._dao, Path(path))
            QMessageBox.information(self, "Готово", f"Тест экспортирован:\n{path}")
        except Exception as exc:
            logger.error("Export failed: %s", exc)
            QMessageBox.warning(self, "Ошибка", f"Не удалось экспортировать тест:\n{exc}")

    def _on_delete_clicked(self) -> None:
        if self._test_data is None:
            return
        reply = QMessageBox.question(
            self,
            "Удалить тест",
            f"Удалить тест «{self._test_data.name}»?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            self._dao.delete(self._test_data.id)
            self.test_deleted.emit()
        except OSError as exc:
            logger.error("Failed to delete test: %s", exc)
            QMessageBox.warning(self, "Ошибка", f"Не удалось удалить тест: {exc}")

    # -- AOI actions ---------------------------------------------------------

    _editing_aoi_idx: int | None = None

    def _on_aoi_start_drawing(self) -> None:
        self._editing_aoi_idx = None
        self._aoi_canvas.start_drawing()
        self._aoi_add_btn.setVisible(False)
        self._aoi_form.setVisible(True)
        self._aoi_name_input.clear()
        self._aoi_first_fix_cb.setChecked(False)
        self._aoi_current_color = QColor(0, 220, 100)
        self._update_color_btn()
        self._aoi_canvas.set_draw_color(self._aoi_current_color)
        self._aoi_name_input.setFocus()

    def _on_aoi_edit(self, idx: int) -> None:
        aois = self._aoi_canvas.get_aois()
        if idx < 0 or idx >= len(aois):
            return
        self._editing_aoi_idx = idx
        roi = aois[idx]
        self._aoi_add_btn.setVisible(False)
        self._aoi_form.setVisible(True)
        self._aoi_name_input.setText(roi.get("name", ""))
        self._aoi_first_fix_cb.setChecked(roi.get("first_fixation", False))
        self._aoi_current_color = QColor(roi.get("color", "#00dc64"))
        self._update_color_btn()
        self._aoi_name_input.setFocus()

    def _on_aoi_cancel_drawing(self) -> None:
        if self._editing_aoi_idx is not None:
            self._editing_aoi_idx = None
        else:
            self._aoi_canvas.cancel_drawing()
            self._aoi_canvas.clear_pending()
        self._aoi_form.setVisible(False)
        self._aoi_add_btn.setVisible(True)

    def _on_aoi_save_region(self) -> None:
        name = self._aoi_name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Ошибка", "Введите название области")
            return

        if self._editing_aoi_idx is not None:
            aois = self._aoi_canvas.get_aois()
            idx = self._editing_aoi_idx
            if 0 <= idx < len(aois):
                aois[idx]["name"] = name
                aois[idx]["color"] = self._aoi_current_color.name()
                aois[idx]["first_fixation"] = self._aoi_first_fix_cb.isChecked()
                self._aoi_canvas.set_image(self._aoi_canvas._pixmap, aois)
            self._editing_aoi_idx = None
        else:
            pending = self._aoi_canvas.get_pending_points()
            if not pending:
                return
            aoi = {
                "name": name,
                "color": self._aoi_current_color.name(),
                "first_fixation": self._aoi_first_fix_cb.isChecked(),
                "points": [{"x": x, "y": y} for x, y in pending],
            }
            self._aoi_canvas.clear_pending()
            self._aoi_canvas.add_aoi(aoi)

        self._aoi_form.setVisible(False)
        self._aoi_add_btn.setVisible(True)
        self._rebuild_aoi_list()
        self._persist_aoi()

    def _on_aoi_pick_color(self) -> None:
        color = QColorDialog.getColor(self._aoi_current_color, self, "Цвет области")
        if color.isValid():
            self._aoi_current_color = color
            self._update_color_btn()
            self._aoi_canvas.set_draw_color(color)
            if self._editing_aoi_idx is not None:
                aois = self._aoi_canvas.get_aois()
                idx = self._editing_aoi_idx
                if 0 <= idx < len(aois):
                    aois[idx]["color"] = color.name()
                    self._aoi_canvas.set_image(self._aoi_canvas._pixmap, aois)
                    self._rebuild_aoi_list()

    def _update_color_btn(self) -> None:
        c = self._aoi_current_color.name()
        self._aoi_color_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {c};
                border: 1px solid {BORDER_COLOR};
                border-radius: {CORNER_RADIUS}px;
            }}
            QPushButton:hover {{ border-color: {TEXT_PRIMARY}; }}
        """)

    def _rebuild_aoi_list(self) -> None:
        while self._aoi_list_container.count():
            item = self._aoi_list_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for idx, roi in enumerate(self._aoi_canvas.get_aois()):
            row = QPushButton()
            row.setFixedHeight(32)
            row.setCursor(Qt.CursorShape.PointingHandCursor)
            row.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; border: none; border-radius: 4px;
                    padding: 0 4px;
                }}
                QPushButton:hover {{ background: {BG_SIDEBAR}; }}
            """)
            row.clicked.connect(lambda _, i=idx: self._on_aoi_edit(i))
            hl = QHBoxLayout(row)
            hl.setContentsMargins(4, 0, 4, 0)
            hl.setSpacing(8)

            swatch = QLabel()
            swatch.setFixedSize(16, 16)
            color = roi.get("color", "#00dc64")
            swatch.setStyleSheet(f"background-color: {color}; border-radius: 3px;")
            swatch.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            hl.addWidget(swatch)

            name = QLabel(roi.get("name", ""))
            name.setFont(QFont(FONT_FAMILY, 12))
            name.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")
            name.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            hl.addWidget(name)

            if roi.get("first_fixation"):
                tag = QLabel("[1]")
                tag.setFont(QFont(FONT_FAMILY, 11))
                tag.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")
                tag.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                hl.addWidget(tag)

            hl.addStretch()

            del_btn = QPushButton("✕")
            del_btn.setFixedSize(24, 24)
            del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            del_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {ERROR_COLOR};
                    border: none; font-size: 14px;
                }}
                QPushButton:hover {{ color: white; background: {ERROR_COLOR}; border-radius: 4px; }}
            """)
            del_btn.clicked.connect(lambda _, i=idx: self._on_aoi_delete(i))
            hl.addWidget(del_btn)

            self._aoi_list_container.addWidget(row)

    def _on_aoi_delete(self, idx: int) -> None:
        self._aoi_canvas.remove_aoi(idx)
        self._rebuild_aoi_list()
        self._persist_aoi()

    def _persist_aoi(self) -> None:
        if self._test_data is None:
            return
        aois = self._aoi_canvas.get_aois()
        try:
            self._dao.save_aoi(self._test_data.id, aois)
            self._test_data.aoi = aois
        except Exception as exc:
            logger.error("Failed to save AOI: %s", exc)
            QMessageBox.warning(self, "Ошибка", f"Не удалось сохранить AOI: {exc}")

    # -- validation display --------------------------------------------------

    def _show_errors(self, errors: dict[str, str]) -> None:
        self._name_error.setText(errors.get("name", ""))
        self._name_error.setVisible("name" in errors)

        self._image_error.setText(errors.get("image", ""))
        self._image_error.setVisible("image" in errors)

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _make_error_label() -> QLabel:
        lbl = QLabel()
        lbl.setFont(QFont(FONT_FAMILY, 12))
        lbl.setStyleSheet(f"color: {ERROR_COLOR}; background: transparent;")
        lbl.setVisible(False)
        return lbl
