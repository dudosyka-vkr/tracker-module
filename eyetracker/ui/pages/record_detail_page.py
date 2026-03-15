"""Record detail page: per-image metrics tabs + export."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from eyetracker.core.report_export import export_record_zip
from eyetracker.core.time_fmt import format_datetime
from eyetracker.data.record.service import Record, RecordService
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
    """Detail view for a single record with per-image tabs."""

    def __init__(
        self,
        record_service: RecordService,
        record_id: str,
        test_name: str,
        on_back: Callable[[], None],
    ):
        super().__init__()
        self._record_service = record_service
        self._record_id = record_id
        self._test_name = test_name
        self._on_back = on_back
        self._record: Record | None = None
        self._tab_buttons: list[QPushButton] = []
        self._active_tab = 0

        self.setStyleSheet(f"background-color: {BG_MAIN};")
        self._build_ui()
        self._load_record()

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
        self._tab_bar = QHBoxLayout()
        self._tab_bar.setSpacing(4)
        self._tab_container = QWidget()
        self._tab_container.setStyleSheet("background: transparent;")
        self._tab_container.setLayout(self._tab_bar)
        self._layout.addWidget(self._tab_container)

        # JSON content area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                background-color: {BG_SIDEBAR};
                border: 1px solid {BORDER_COLOR};
                border-radius: {CORNER_RADIUS}px;
            }}
        """)

        self._json_label = QLabel()
        self._json_label.setFont(QFont("Menlo", 12))
        self._json_label.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent; padding: 16px;")
        self._json_label.setWordWrap(True)
        self._json_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._json_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        scroll.setWidget(self._json_label)
        self._layout.addWidget(scroll, stretch=1)

    def _load_record(self) -> None:
        self._record = self._record_service.load(self._record_id)
        if self._record is None:
            self._title_label.setText("Отчет не найден")
            return

        self._title_label.setText(f"Отчет: {self._test_name}")
        self._subtitle_label.setText(
            f"{self._record.user_login}  ·  {format_datetime(self._record.started_at)}"
        )

        self._build_tabs()
        if self._record.items:
            self._select_tab(0)

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
        self._show_item_metrics(index)

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

    def _show_item_metrics(self, index: int) -> None:
        if self._record is None or index >= len(self._record.items):
            return
        item = self._record.items[index]
        metrics_dict = asdict(item.metrics)
        pretty = json.dumps(metrics_dict, indent=2, ensure_ascii=False)
        self._json_label.setText(pretty)

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
            export_record_zip(self._record, Path(path))
            QMessageBox.information(self, "Готово", "Отчет сохранён.")
        except OSError as exc:
            QMessageBox.warning(self, "Ошибка", f"Не удалось сохранить: {exc}")
