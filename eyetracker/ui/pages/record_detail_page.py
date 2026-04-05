"""Record detail page: per-image heatmap tabs + export."""

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

from eyetracker.core.fixation_map import generate_fixation_map
from eyetracker.core.heatmap import generate_heatmap
from eyetracker.core.report_export import export_record_zip
from eyetracker.core.time_fmt import format_datetime
from eyetracker.data.record.service import Record, RecordItem, RecordService
from eyetracker.data.test import TestDao, TestData
from eyetracker.ui.theme import (
    BG_MAIN,
    BG_SIDEBAR,
    BG_SIDEBAR_ACTIVE,
    BG_SIDEBAR_HOVER,
    BORDER_COLOR,
    BUTTON_BG,
    BUTTON_HOVER,
    CORNER_RADIUS,
    FONT_FAMILY,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


_BADGE_W = 108
_BADGE_H = 61  # ~10% smaller than 120×68


class _FixationBadge(QWidget):
    """Small card that shows fixation number + emotion and fires on mouse-enter."""

    def __init__(self, number: int, emotion: str, on_enter,
                 time_ms: int | None = None, parent=None):
        super().__init__(parent)
        self._on_enter = on_enter
        self.setFixedSize(_BADGE_W, _BADGE_H)
        self.setObjectName("FixationBadge")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.setStyleSheet(f"""
            #FixationBadge {{
                background-color: {BG_SIDEBAR};
                border: 1px solid {BORDER_COLOR};
                border-radius: {CORNER_RADIUS}px;
            }}
            #FixationBadge:hover {{
                border-color: {BUTTON_HOVER};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(1)

        num_lbl = QLabel(f"#{number} {emotion}")
        num_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        num_lbl.setFont(QFont(FONT_FAMILY, 11, QFont.Weight.Bold))
        num_lbl.setStyleSheet(f"background: transparent; color: {TEXT_PRIMARY};")
        layout.addWidget(num_lbl)

        if time_ms is not None:
            time_lbl = QLabel(f"{time_ms} ms")
            time_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            time_lbl.setFont(QFont(FONT_FAMILY, 9))
            time_lbl.setStyleSheet(f"background: transparent; color: {TEXT_SECONDARY};")
            layout.addWidget(time_lbl)

    def enterEvent(self, event) -> None:
        self._on_enter()
        super().enterEvent(event)


class RecordDetailPage(QWidget):
    """Detail view for a single record with per-image heatmap tabs."""

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
        self._tab_buttons: list[QPushButton] = []
        self._active_tab = 0

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

        # Tab bar
        tab_container = QWidget()
        tab_container.setStyleSheet("background: transparent;")
        self._tab_bar = QHBoxLayout(tab_container)
        self._tab_bar.setSpacing(4)
        self._layout.addWidget(tab_container)

        # Scroll area for the heatmap image
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._content_widget = QWidget()
        self._content_widget.setStyleSheet("background: transparent;")
        self._content_layout = QVBoxLayout(self._content_widget)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
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

        self._build_tabs()
        if self._record.items:
            self._select_tab(0)

    # ------------------------------------------------------------------
    # Tabs
    # ------------------------------------------------------------------

    def _build_tabs(self) -> None:
        if self._record is None:
            return
        for i in range(len(self._record.items)):
            btn = QPushButton(str(i + 1))
            btn.setFixedSize(40, 32)
            btn.setFont(QFont(FONT_FAMILY, 13))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, idx=i: self._select_tab(idx))
            self._tab_buttons.append(btn)
            self._tab_bar.addWidget(btn)
        self._tab_bar.addStretch()
        self._update_tab_styles()

    def _select_tab(self, index: int) -> None:
        self._active_tab = index
        self._update_tab_styles()
        self._show_item(index)

    def _update_tab_styles(self) -> None:
        for i, btn in enumerate(self._tab_buttons):
            if i == self._active_tab:
                btn.setChecked(True)
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {BG_SIDEBAR_ACTIVE};
                        color: white;
                        border: none;
                        border-radius: {CORNER_RADIUS}px;
                    }}
                """)
            else:
                btn.setChecked(False)
                btn.setStyleSheet(f"""
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

    # ------------------------------------------------------------------
    # Content rendering
    # ------------------------------------------------------------------

    def _clear_content(self) -> None:
        while self._content_layout.count():
            child = self._content_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _show_item(self, index: int) -> None:
        if self._record is None or index >= len(self._record.items):
            return

        self._clear_content()
        item = self._record.items[index]

        self._content_layout.addWidget(self._build_heatmap_widget(item))
        self._content_layout.addWidget(self._build_fixation_list(item))
        self._content_layout.addStretch()

    def _build_heatmap_widget(self, item: RecordItem) -> QWidget:
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(0, 0, 0, 0)
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

        image_path = self._resolve_image_path(item)
        if image_path is None or not image_path.exists():
            label.setText(f"Изображение не найдено: {item.image_filename}")
        else:
            try:
                rgb = generate_heatmap(image_path, item.metrics.gaze_groups)
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

    def _build_fixation_list(self, item: RecordItem) -> QWidget:
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(0, 16, 0, 0)
        vbox.setSpacing(8)

        fixations = item.metrics.fixations
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
        image_path = self._resolve_image_path(item)

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

        # --- Badge grid below the preview (4 per row, centered) ---
        grid_widget = QWidget()
        grid_widget.setStyleSheet("background: transparent;")
        grid_vbox = QVBoxLayout(grid_widget)
        grid_vbox.setContentsMargins(0, 8, 0, 0)
        grid_vbox.setSpacing(8)

        for row_start in range(0, len(sorted_fixations), 4):
            chunk = sorted_fixations[row_start:row_start + 4]
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
                    emotion=fx.get("emotion", "—"),
                    on_enter=lambda i=idx, _fx=sorted_fixations, _path=image_path, _lbl=preview:
                        self._update_fixation_preview(_fx, i, _path, _lbl),
                    time_ms=fx.get("time_ms"),
                )
                row_h.addWidget(badge)
            row_h.addStretch()
            grid_vbox.addWidget(row_w)

        vbox.addWidget(grid_widget)
        return container

    def _update_fixation_preview(
        self,
        fixations: list[dict],
        row: int,
        image_path,
        label: QLabel,
    ) -> None:
        if row < 0 or row >= len(fixations) or image_path is None or not image_path.exists():
            return
        try:
            rgb = generate_fixation_map(image_path, fixations[row], number=row + 1)
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

    def _resolve_image_path(self, item: RecordItem) -> Path | None:
        if self._test_dao is None or self._test_data is None:
            return None
        return self._test_dao.get_image_path(self._test_data, item.image_filename)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _on_export(self) -> None:
        if self._record is None:
            return

        suggested = f"report_{self._record.test_id}_{self._record.id}.zip"
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
