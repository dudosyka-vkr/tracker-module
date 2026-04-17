"""Record detail page: heatmap, gaze points, fixations + export."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QImage, QPixmap
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from eyetracker.core.aoi_sequence_map import generate_aoi_sequence_map
from eyetracker.core.roi import compute_tge
from eyetracker.core.fixation_map import generate_all_fixations_map, generate_fixation_map
from eyetracker.core.gaze_points_map import generate_gaze_points_map, generate_saccade_map
from eyetracker.core.heatmap import generate_heatmap
from eyetracker.core.report_export import export_record_zip
from eyetracker.core.roi import overlay_rois
from eyetracker.core.time_fmt import format_datetime
from eyetracker.data.record.service import Record, RecordService
from eyetracker.data.test import TestDao, TestData
from eyetracker.ui.theme import (
    BG_MAIN,
    BG_SIDEBAR,
    BORDER_COLOR,
    BUTTON_BG,
    BUTTON_HOVER,
    CORNER_RADIUS,
    FONT_FAMILY,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


_BADGE_W = 120
_BADGE_H = 76




class _HoverLabel(QLabel):
    """QLabel that shows a custom tooltip popup on hover."""

    def __init__(self, text: str, tooltip: str, parent: QWidget | None = None):
        super().__init__(text, parent)
        self._tooltip_text = tooltip
        self._tooltip_popup: QLabel | None = None

    def enterEvent(self, event) -> None:  # noqa: N802
        popup = QLabel(self._tooltip_text)
        popup.setWindowFlags(
            Qt.WindowType.ToolTip
        )
        popup.setFont(QFont(FONT_FAMILY, 11))
        popup.setStyleSheet(
            f"color: {TEXT_PRIMARY};"
            f" background-color: {BG_SIDEBAR};"
            f" border: 1px solid {BORDER_COLOR};"
            f" border-radius: 4px;"
            f" padding: 4px 8px;"
        )
        popup.adjustSize()
        pos = self.mapToGlobal(self.rect().bottomLeft())
        popup.move(pos)
        popup.show()
        self._tooltip_popup = popup
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self._tooltip_popup is not None:
            self._tooltip_popup.close()
            self._tooltip_popup = None
        super().leaveEvent(event)


class _FixationBadge(QWidget):
    """Compact card showing fixation number, start time and duration."""

    _NORMAL_SS = f"""
        QWidget {{
            background-color: {BG_SIDEBAR};
            border: 1px solid {BORDER_COLOR};
            border-radius: {CORNER_RADIUS}px;
        }}
    """
    _SELECTED_SS = f"""
        QWidget {{
            background-color: {BG_SIDEBAR};
            border: 2px solid {BUTTON_BG};
            border-radius: {CORNER_RADIUS}px;
        }}
    """

    def __init__(
        self,
        number: int,
        on_enter: Callable[[], None] | None = None,
        on_leave: Callable[[], None] | None = None,
        on_click: Callable[[], None] | None = None,
        time_ms: int | None = None,
        duration_ms: int | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setFixedSize(_BADGE_W, _BADGE_H)
        self._on_enter = on_enter
        self._on_leave = on_leave
        self._on_click = on_click
        self._selected = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.setStyleSheet(self._NORMAL_SS)

        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(4, 3, 4, 3)
        vbox.setSpacing(0)
        vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)

        num_lbl = QLabel(f"#{number}")
        num_lbl.setFont(QFont(FONT_FAMILY, 14, QFont.Weight.Bold))
        num_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        num_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent; border: none;")
        num_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        vbox.addWidget(num_lbl)

        if time_ms is not None:
            s_lbl = QLabel(f"{time_ms} мс")
            s_lbl.setFont(QFont(FONT_FAMILY, 10))
            s_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            s_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent; border: none;")
            s_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            vbox.addWidget(s_lbl)

        if duration_ms is not None:
            d_lbl = QLabel(f"⏱ {duration_ms} мс")
            d_lbl.setFont(QFont(FONT_FAMILY, 10))
            d_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            d_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent; border: none;")
            d_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            vbox.addWidget(d_lbl)

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self.setStyleSheet(self._SELECTED_SS if selected else self._NORMAL_SS)

    def enterEvent(self, event) -> None:  # noqa: N802
        super().enterEvent(event)
        if self._on_enter is not None:
            self._on_enter()

    def leaveEvent(self, event) -> None:  # noqa: N802
        super().leaveEvent(event)
        if self._on_leave is not None:
            self._on_leave()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        event.accept()
        if self._on_click is not None:
            self._on_click()


class RecordDetailPage(QWidget):
    """Detail view for a single test record."""

    def __init__(
        self,
        record_service: RecordService,
        record_id: str,
        test_name: str,
        on_back: Callable[[], None],
        test_dao: TestDao | None = None,
    ):
        super().__init__()
        self._record_service = record_service
        self._record_id = record_id
        self._test_name = test_name
        self._on_back = on_back
        self._test_dao = test_dao
        self._record: Record | None = None
        self._test_data: TestData | None = None

        self.setStyleSheet(f"background-color: {BG_MAIN};")
        self._build_ui()
        self._load_record()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(40, 40, 40, 40)
        self._layout.setSpacing(12)

        # Top row: back + export
        top_row = QHBoxLayout()
        back_btn = QPushButton("← Назад")
        back_btn.setFont(QFont(FONT_FAMILY, 13))
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {BUTTON_BG};
                border: none;
                padding: 4px 8px;
            }}
            QPushButton:hover {{ color: {BUTTON_HOVER}; }}
        """)
        back_btn.clicked.connect(lambda _checked: self._on_back())
        top_row.addWidget(back_btn)
        top_row.addStretch()

        export_btn = QPushButton("Выгрузить отчет")
        export_btn.setFont(QFont(FONT_FAMILY, 13, QFont.Weight.Bold))
        export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        export_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {BUTTON_BG};
                color: white;
                border: none;
                border-radius: {CORNER_RADIUS}px;
                padding: 8px 20px;
            }}
            QPushButton:hover {{ background-color: {BUTTON_HOVER}; }}
        """)
        export_btn.clicked.connect(self._on_export)
        top_row.addWidget(export_btn)
        self._layout.addLayout(top_row)

        # Title
        self._title_label = QLabel()
        self._title_label.setFont(QFont(FONT_FAMILY, 28, QFont.Weight.Bold))
        self._title_label.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")
        self._layout.addWidget(self._title_label)

        # Subtitle: user + date
        self._subtitle_label = QLabel()
        self._subtitle_label.setFont(QFont(FONT_FAMILY, 14))
        self._subtitle_label.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")
        self._layout.addWidget(self._subtitle_label)

        # Scroll area for content
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._content_widget = QWidget()
        self._content_widget.setStyleSheet("background: transparent;")
        self._content_layout = QVBoxLayout(self._content_widget)
        self._content_layout.setContentsMargins(0, 0, 16, 24)
        self._content_layout.setSpacing(0)
        self._scroll.setWidget(self._content_widget)
        self._layout.addWidget(self._scroll, stretch=1)

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_record(self) -> None:
        self._record = self._record_service.load(self._record_id)
        if self._record is None:
            self._title_label.setText("Отчет не найден")
            return

        self._title_label.setText(f"Отчет: {self._test_name}")
        self._subtitle_label.setText(
            f"{self._record.user_login}  ·  {format_datetime(self._record.started_at)}"
        )

        if self._test_dao is not None:
            self._test_data = self._test_dao.load(self._record.test_id)

        self._show_content()

    # ------------------------------------------------------------------
    # Content rendering
    # ------------------------------------------------------------------

    def _clear_content(self) -> None:
        while self._content_layout.count():
            child = self._content_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _show_content(self) -> None:
        if self._record is None:
            return

        self._clear_content()
        metrics = self._record.metrics

        roi_widget = self._build_roi_metrics_widget()
        if roi_widget is not None:
            self._content_layout.addWidget(roi_widget)
        self._content_layout.addWidget(self._build_heatmap_widget())
        aoi_seq_widget = self._build_aoi_sequence_widget()
        if aoi_seq_widget is not None:
            self._content_layout.addWidget(aoi_seq_widget)
        self._content_layout.addWidget(self._build_gaze_points_widget())
        self._content_layout.addWidget(self._build_saccade_map_widget())
        self._content_layout.addWidget(self._build_fixation_list())
        self._content_layout.addStretch()

    def _build_heatmap_widget(self) -> QWidget:
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(0, 16, 0, 0)
        vbox.setSpacing(8)

        heading = QLabel("Тепловая карта")
        heading.setFont(QFont(FONT_FAMILY, 16, QFont.Weight.Bold))
        heading.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")
        vbox.addWidget(heading)

        label = QLabel()
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        label.setFixedHeight(540)
        label.setStyleSheet(
            f"background-color: {BG_SIDEBAR}; border: 1px solid {BORDER_COLOR};"
            f" border-radius: {CORNER_RADIUS}px; color: {TEXT_SECONDARY};"
        )

        image_path = self._resolve_image_path()
        if image_path is None or not image_path.exists():
            label.setText("Изображение не найдено")
        else:
            try:
                rgb = generate_heatmap(image_path, self._record.metrics.gaze_groups)
                rois = (
                    self._test_data.aoi
                    if self._test_data is not None else []
                )
                rgb = overlay_rois(rgb, rois)
                label.setPixmap(
                    _rgb_array_to_pixmap(rgb).scaled(
                        960, 540,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
            except Exception:
                label.setText("Ошибка генерации тепловой карты")

        vbox.addWidget(label)
        return container

    def _build_gaze_points_widget(self) -> QWidget:
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(0, 16, 0, 0)
        vbox.setSpacing(8)

        heading = QLabel("Карта точек взгляда")
        heading.setFont(QFont(FONT_FAMILY, 16, QFont.Weight.Bold))
        heading.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")
        vbox.addWidget(heading)

        label = QLabel()
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        label.setFixedHeight(540)
        label.setStyleSheet(
            f"background-color: {BG_SIDEBAR}; border: 1px solid {BORDER_COLOR};"
            f" border-radius: {CORNER_RADIUS}px; color: {TEXT_SECONDARY};"
        )

        image_path = self._resolve_image_path()
        if image_path is None or not image_path.exists():
            label.setText("Изображение не найдено")
        else:
            try:
                rgb = generate_gaze_points_map(image_path, self._record.metrics.gaze_groups)
                label.setPixmap(
                    _rgb_array_to_pixmap(rgb).scaled(
                        960, 540,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
            except Exception:
                label.setText("Ошибка генерации карты точек")

        vbox.addWidget(label)
        return container

    def _build_saccade_map_widget(self) -> QWidget:
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(0, 16, 0, 0)
        vbox.setSpacing(8)

        heading = QLabel("Карта саккад")
        heading.setFont(QFont(FONT_FAMILY, 16, QFont.Weight.Bold))
        heading.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")
        vbox.addWidget(heading)

        label = QLabel()
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        label.setFixedHeight(540)
        label.setStyleSheet(
            f"background-color: {BG_SIDEBAR}; border: 1px solid {BORDER_COLOR};"
            f" border-radius: {CORNER_RADIUS}px; color: {TEXT_SECONDARY};"
        )

        image_path = self._resolve_image_path()
        if image_path is None or not image_path.exists():
            label.setText("Изображение не найдено")
        else:
            try:
                rgb = generate_saccade_map(image_path, self._record.metrics.saccades)
                label.setPixmap(
                    _rgb_array_to_pixmap(rgb).scaled(
                        960, 540,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
            except Exception:
                label.setText("Ошибка генерации карты саккад")

        vbox.addWidget(label)
        return container

    def _build_fixation_list(self) -> QWidget:
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(0, 16, 0, 0)
        vbox.setSpacing(8)

        fixations = self._record.metrics.fixations
        heading = QLabel(f"Фиксации ({len(fixations)})")
        heading.setFont(QFont(FONT_FAMILY, 16, QFont.Weight.Bold))
        heading.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")
        vbox.addWidget(heading)

        if not fixations:
            empty = QLabel("Фиксации не обнаружены")
            empty.setFont(QFont(FONT_FAMILY, 13))
            empty.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")
            vbox.addWidget(empty)
            return container

        sorted_fixations = sorted(fixations, key=lambda fx: 0 if fx.get("is_first") else 1)
        image_path = self._resolve_image_path()
        item_rois = (
            self._test_data.aoi
            if self._test_data is not None else []
        )

        # --- Preview label ---
        preview = QLabel()
        preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview.setStyleSheet(
            f"background-color: {BG_SIDEBAR}; border: 1px solid {BORDER_COLOR};"
            f" border-radius: {CORNER_RADIUS}px; color: {TEXT_SECONDARY};"
        )
        preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        preview.setFixedHeight(540)
        preview.setText("Наведите на строку таблицы для предпросмотра")
        preview.setFont(QFont(FONT_FAMILY, 13))
        vbox.addWidget(preview)

        # --- Badge grid below the preview (8 per row, centered) ---
        all_badges: list[_FixationBadge] = []
        grid_widget = QWidget()
        grid_widget.setStyleSheet("background: transparent;")
        grid_vbox = QVBoxLayout(grid_widget)
        grid_vbox.setContentsMargins(0, 8, 0, 0)
        grid_vbox.setSpacing(8)

        selected_indices: set[int] = set()

        def _render_indices(indices: list[int]) -> None:
            if not indices or image_path is None or not image_path.exists():
                return
            try:
                fxs = [sorted_fixations[i] for i in indices]
                nums = [i + 1 for i in indices]
                rgb = generate_all_fixations_map(image_path, fxs, numbers=nums)
                if item_rois:
                    rgb = overlay_rois(rgb, item_rois)
            except Exception:
                return
            preview.setPixmap(
                _rgb_array_to_pixmap(rgb).scaled(
                    960, 540,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

        def _render_selected() -> None:
            _render_indices(sorted(selected_indices))

        def _render_with_hover(hovered_idx: int) -> None:
            indices = sorted(selected_indices | {hovered_idx})
            _render_indices(indices)

        def _toggle_badge(idx: int) -> None:
            badge = all_badges[idx]
            if badge._selected:
                badge.set_selected(False)
                selected_indices.discard(idx)
            else:
                badge.set_selected(True)
                selected_indices.add(idx)
            if selected_indices:
                _render_selected()
            else:
                preview.setText("Наведите на строку таблицы для предпросмотра")

        for row_start in range(0, len(sorted_fixations), 8):
            chunk = sorted_fixations[row_start:row_start + 8]
            row_w = QWidget()
            row_w.setStyleSheet("background: transparent;")
            row_h = QHBoxLayout(row_w)
            row_h.setContentsMargins(0, 0, 0, 0)
            row_h.setSpacing(8)
            row_h.addStretch()
            for offset, fx in enumerate(chunk):
                idx = row_start + offset
                badge = _FixationBadge(
                    number=idx + 1,
                    on_enter=lambda i=idx: _render_with_hover(i),
                    on_leave=lambda: _render_selected() if selected_indices else
                        preview.setText("Наведите на строку таблицы для предпросмотра"),
                    on_click=lambda i=idx: _toggle_badge(i),
                    time_ms=fx.get("start_ms"),
                    duration_ms=fx.get("duration_ms"),
                )
                all_badges.append(badge)
                row_h.addWidget(badge)
            row_h.addStretch()
            grid_vbox.addWidget(row_w)

        vbox.addWidget(grid_widget)

        if all_badges:
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, lambda: _toggle_badge(0))

        return container

    def _update_fixation_preview(
        self,
        fixations: list[dict],
        row: int,
        image_path,
        label: QLabel,
        rois: list[dict] | None = None,
    ) -> None:
        if row < 0 or row >= len(fixations) or image_path is None or not image_path.exists():
            return
        try:
            rgb = generate_fixation_map(image_path, fixations[row], number=row + 1)
            if rois:
                rgb = overlay_rois(rgb, rois)
        except Exception:
            return
        pixmap = _rgb_array_to_pixmap(rgb)
        label.setPixmap(
            pixmap.scaled(
                960, 540,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _resolve_image_path(self) -> Path | None:
        if self._test_dao is None or self._test_data is None:
            return None
        return self._test_dao.get_image_path(self._test_data)

    def _build_roi_metrics_widget(self) -> QWidget | None:
        rois = self._record.metrics.roi_metrics
        if not rois:
            return None

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(8)

        heading = QLabel("Зоны интереса")
        heading.setFont(QFont(FONT_FAMILY, 16, QFont.Weight.Bold))
        heading.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")
        vbox.addWidget(heading)

        for roi in rois:
            row = QWidget()
            row.setStyleSheet(f"""
                QWidget {{
                    background-color: {BG_SIDEBAR};
                    border: 1px solid {BORDER_COLOR};
                    border-radius: {CORNER_RADIUS}px;
                }}
            """)
            row.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(14, 10, 14, 10)
            row_layout.setSpacing(10)

            # Color swatch
            color_str = roi.get("color", "#00dc64")
            swatch = QLabel()
            swatch.setFixedSize(14, 14)
            swatch.setStyleSheet(f"""
                background-color: {color_str};
                border-radius: 3px;
                border: none;
            """)
            row_layout.addWidget(swatch)

            # Name + optional [1] badge
            name_parts = []
            if roi.get("first_fixation_required"):
                name_parts.append("[1]")
            name_parts.append(roi.get("name", ""))
            name_lbl = QLabel("  ".join(name_parts))
            name_lbl.setFont(QFont(FONT_FAMILY, 13))
            name_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")
            row_layout.addWidget(name_lbl, stretch=1)

            # Hit indicator
            hit = roi.get("hit", False)
            hit_lbl = QLabel("✓  Да" if hit else "✗  Нет")
            hit_lbl.setFont(QFont(FONT_FAMILY, 13, QFont.Weight.Bold))
            hit_color = "#4caf50" if hit else "#f44336"
            hit_lbl.setStyleSheet(f"color: {hit_color}; background: transparent;")
            row_layout.addWidget(hit_lbl)

            # First fixation time inside this AOI
            aoi_first = roi.get("aoi_first_fixation")
            aoi_fix_lbl = _HoverLabel(
                f"⏱ {aoi_first} мс" if aoi_first is not None else "⏱ —",
                tooltip="Время первой фиксации",
            )
            aoi_fix_lbl.setFont(QFont(FONT_FAMILY, 13))
            aoi_fix_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")
            row_layout.addWidget(aoi_fix_lbl)

            # Revisits
            revisits = roi.get("revisits", 0)
            revisits_lbl = _HoverLabel(
                f"↩ {revisits}",
                tooltip="Количество \nповторных \nзаходов",
            )
            revisits_lbl.setFont(QFont(FONT_FAMILY, 13))
            revisits_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")
            row_layout.addWidget(revisits_lbl)

            vbox.addWidget(row)

        return container

    def _build_tge_widget(self) -> QWidget | None:
        tge = self._record.metrics.tge
        if tge is None:
            tge = compute_tge(self._record.metrics.aoi_sequence)
        if tge is None:
            return None

        tge_row = QWidget()
        tge_row.setStyleSheet(f"""
            QWidget {{
                background-color: {BG_SIDEBAR};
                border: 1px solid {BORDER_COLOR};
                border-radius: {CORNER_RADIUS}px;
            }}
        """)
        tge_row.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        tge_layout = QHBoxLayout(tge_row)
        tge_layout.setContentsMargins(14, 10, 14, 10)
        tge_layout.setSpacing(10)

        tge_name = _HoverLabel(
            "Энтропия переходов",
            tooltip=(
                "Transition Gaze Entropy — энтропия переходов между зонами.\n"
                "Низкое значение: взгляд следует чёткому маршруту.\n"
                "Высокое значение: переходы случайны, интерфейс запутан."
            ),
        )
        tge_name.setFont(QFont(FONT_FAMILY, 13))
        tge_name.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")
        tge_layout.addWidget(tge_name, stretch=1)

        tge_val = QLabel(f"{tge:.4f}")
        tge_val.setFont(QFont(FONT_FAMILY, 13, QFont.Weight.Bold))
        tge_val.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")
        tge_layout.addWidget(tge_val)

        return tge_row

    def _build_aoi_sequence_widget(self) -> QWidget | None:
        if self._record is None:
            return None
        aoi_sequence = self._record.metrics.aoi_sequence
        if not aoi_sequence:
            return None
        rois = self._test_data.aoi if self._test_data is not None else []

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(0, 16, 0, 0)
        vbox.setSpacing(8)

        heading = QLabel("Переходы между зонами интереса")
        heading.setFont(QFont(FONT_FAMILY, 16, QFont.Weight.Bold))
        heading.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")
        vbox.addWidget(heading)

        label = QLabel()
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        label.setFixedHeight(540)
        label.setStyleSheet(
            f"background-color: {BG_SIDEBAR}; border: 1px solid {BORDER_COLOR};"
            f" border-radius: {CORNER_RADIUS}px; color: {TEXT_SECONDARY};"
        )

        image_path = self._resolve_image_path()
        if image_path is None or not image_path.exists():
            label.setText("Изображение не найдено")
        else:
            try:
                rgb = generate_aoi_sequence_map(image_path, rois, aoi_sequence)
                label.setPixmap(
                    _rgb_array_to_pixmap(rgb).scaled(
                        960, 540,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
            except Exception:
                label.setText("Ошибка генерации карты переходов")

        vbox.addWidget(label)

        tge_widget = self._build_tge_widget()
        if tge_widget is not None:
            vbox.addWidget(tge_widget)

        return container

    # ------------------------------------------------------------------
    # Fixation recalculation
    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _on_export(self) -> None:
        if self._record is None:
            return

        def _safe(s: str) -> str:
            return "".join(c if c.isalnum() or c in "-_" else "_" for c in s)

        dt_part = self._record.started_at[:19].replace("T", "_").replace(":", "-")
        suggested = f"{_safe(self._test_name)}_{dt_part}_{_safe(self._record.user_login)}.zip"
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить отчет", suggested, "Zip Archive (*.zip)"
        )
        if not path:
            return

        try:
            export_record_zip(self._record, Path(path), self._test_dao, self._test_data)
            QMessageBox.information(self, "Готово", "Отчет сохранён.")
        except OSError as exc:
            QMessageBox.warning(self, "Ошибка", f"Не удалось сохранить: {exc}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rgb_array_to_pixmap(rgb: np.ndarray) -> QPixmap:
    h, w, ch = rgb.shape
    img = QImage(rgb.tobytes(), w, h, ch * w, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(img)
