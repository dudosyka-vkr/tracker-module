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

        heatmap_label = self._build_heatmap_label(item)
        self._content_layout.addWidget(heatmap_label)
        self._content_layout.addStretch()

    def _build_heatmap_label(self, item: RecordItem) -> QLabel:
        label = QLabel()
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        label.setStyleSheet("background: transparent;")

        image_path = self._resolve_image_path(item)
        if image_path is None or not image_path.exists():
            label.setText(f"Изображение не найдено: {item.image_filename}")
            label.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")
            return label

        try:
            rgb = generate_heatmap(image_path, item.metrics.gaze_groups)
        except Exception:
            label.setText("Ошибка генерации тепловой карты")
            label.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")
            return label

        pixmap = _rgb_array_to_pixmap(rgb)
        label.setPixmap(
            pixmap.scaled(
                800, 600,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        return label

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
