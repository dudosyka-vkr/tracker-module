"""Records list page: table of test run results."""

from __future__ import annotations

import csv
import io
import json
import os
import sys
import zipfile
from pathlib import Path

_RESOURCES_DIR = (
    Path(getattr(sys, "_MEIPASS", "")) / "eyetracker" / "resources"
    if hasattr(sys, "_MEIPASS")
    else Path(os.path.dirname(__file__)).parent.parent / "resources"
)
from typing import Callable

import logging
import threading

logger = logging.getLogger(__name__)

from PyQt6.QtCore import QDateTime, Qt, QRect, QTimer
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QComboBox,
    QDateTimeEdit,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from eyetracker.core.report_export import export_record_zip
from eyetracker.core.time_fmt import format_datetime
from eyetracker.data.record.service import Record, RecordQuery, RecordService, RecordSummary
from eyetracker.data.test.dao import TestDao, TestData
from eyetracker.ui.theme import (
    BG_MAIN,
    BG_SIDEBAR,
    BORDER_COLOR,
    BUTTON_BG,
    BUTTON_HOVER,
    CARD_BG,
    CORNER_RADIUS,
    FONT_FAMILY,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

_ROI_COLORS = [
    "#0a84ff", "#30d158", "#ff9f0a", "#ff453a", "#bf5af2",
    "#64d2ff", "#ffd60a", "#ff6b6b", "#a8ff78", "#ffb347",
]


class _PieChartWidget(QWidget):
    """Simple pie chart for a single ROI's hit/miss ratio."""

    def __init__(self, roi_name: str, hits: int, total: int, color: str, first_fixation_required: bool = False, parent=None):
        super().__init__(parent)
        self._roi_name = roi_name
        self._hits = hits
        self._total = total
        self._color = color
        self._first_fixation_required = first_fixation_required
        self.setFixedSize(160, 210)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        chart_size = 110
        x = (w - chart_size) // 2
        y = 8
        rect = QRect(x, y, chart_size, chart_size)

        if self._total == 0:
            painter.setBrush(QBrush(QColor("#3a3a3a")))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(rect)
        else:
            hit_angle = int(round(self._hits / self._total * 360 * 16))
            miss_angle = 360 * 16 - hit_angle

            # hit slice
            painter.setBrush(QBrush(QColor(self._color)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPie(rect, 90 * 16, -hit_angle)

            # miss slice
            painter.setBrush(QBrush(QColor("#3a3a3a")))
            painter.drawPie(rect, 90 * 16 - hit_angle, -miss_angle)

        # legend dots + text
        legend_y = y + chart_size + 10
        dot_r = 7

        painter.setBrush(QBrush(QColor(self._color)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(8, legend_y + 3, dot_r, dot_r)
        painter.setPen(QPen(QColor(TEXT_PRIMARY)))
        painter.setFont(QFont(FONT_FAMILY, 11))
        pct = int(round(self._hits / self._total * 100)) if self._total else 0
        painter.drawText(8 + dot_r + 6, legend_y, w - 8 - dot_r - 6, 20, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, f"Попадания: {pct}%")

        legend_y2 = legend_y + 20
        painter.setBrush(QBrush(QColor("#3a3a3a")))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(8, legend_y2 + 3, dot_r, dot_r)
        painter.setPen(QPen(QColor(TEXT_SECONDARY)))
        painter.drawText(8 + dot_r + 6, legend_y2, w - 8 - dot_r - 6, 20, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, f"Промахи: {100 - pct}%")

        # ROI name at bottom
        name_y = legend_y2 + 24
        painter.setPen(QPen(QColor(TEXT_PRIMARY)))
        painter.setFont(QFont(FONT_FAMILY, 11, QFont.Weight.Bold))
        painter.drawText(0, name_y, w, 20, Qt.AlignmentFlag.AlignCenter, self._roi_name)

        if self._first_fixation_required:
            note_y = name_y + 20
            painter.setPen(QPen(QColor("#ff9f0a")))
            painter.setFont(QFont(FONT_FAMILY, 9))
            painter.drawText(0, note_y, w, 16, Qt.AlignmentFlag.AlignCenter, "★ только первая фиксация")






class RecordsListPage(QWidget):
    """Table of record summaries for a given test."""

    def __init__(
        self,
        record_service: RecordService,
        test_id: str,
        test_name: str,
        on_view_report: Callable[[str], None],
        on_back: Callable[[], None],
        test_dao: TestDao | None = None,
        test: TestData | None = None,
    ):
        super().__init__()
        self._record_service = record_service
        self._test_id = test_id
        self._test_name = test_name
        self._on_view_report = on_view_report
        self._on_back = on_back
        self._test_dao = test_dao
        self._test = test
        self._all_summaries: list[RecordSummary] = []
        self._filtered_summaries: list[RecordSummary] = []
        self._roi_names: list[str] = []
        self._roi_filter_combos: dict[str, QComboBox] = {}

        self.setStyleSheet(f"background-color: {BG_MAIN};")
        self._build_ui()
        self._load_records()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── sticky header ────────────────────────────────────────────────────
        header = QWidget()
        header.setStyleSheet(f"background-color: {BG_MAIN};")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(40, 24, 40, 16)
        header_layout.setSpacing(8)

        nav_row = QHBoxLayout()
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
        nav_row.addWidget(back_btn)
        nav_row.addStretch()
        header_layout.addLayout(nav_row)

        title = QLabel(f"Результаты: {self._test_name}")
        title.setFont(QFont(FONT_FAMILY, 28, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")
        header_layout.addWidget(title)

        # ── sync ROI banner (hidden by default) ──────────────────────────────
        self._sync_banner = QWidget()
        self._sync_banner.setStyleSheet(
            f"background-color: #2c2c2e; border: 1px solid {BORDER_COLOR};"
            f" border-radius: {CORNER_RADIUS}px;"
        )
        banner_layout = QHBoxLayout(self._sync_banner)
        banner_layout.setContentsMargins(16, 10, 16, 10)
        banner_layout.setSpacing(12)

        self._sync_label = QLabel(
            "Некоторые записи содержат устаревшие данные зон интереса — "
            "зоны были добавлены или удалены после проведения тестов."
        )
        self._sync_label.setFont(QFont(FONT_FAMILY, 12))
        self._sync_label.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent; border: none;")
        self._sync_label.setWordWrap(True)
        banner_layout.addWidget(self._sync_label, stretch=1)

        self._sync_btn = QPushButton("Синхронизировать зоны интереса")
        self._sync_btn.setFont(QFont(FONT_FAMILY, 12))
        self._sync_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._sync_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {BUTTON_BG};
                color: white;
                border: none;
                border-radius: {CORNER_RADIUS}px;
                padding: 6px 16px;
            }}
            QPushButton:hover {{ background-color: {BUTTON_HOVER}; }}
            QPushButton:disabled {{ background-color: #555; color: #999; }}
        """)
        self._sync_btn.clicked.connect(self._on_sync_clicked)
        banner_layout.addWidget(self._sync_btn)

        self._sync_banner.hide()
        header_layout.addWidget(self._sync_banner)

        outer.addWidget(header)

        # ── scrollable body ───────────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(scroll.Shape.NoFrame)
        scroll.setStyleSheet(f"background-color: {BG_MAIN};")

        body = QWidget()
        body.setStyleSheet(f"background-color: {BG_MAIN};")
        self._body_layout = QVBoxLayout(body)
        self._body_layout.setContentsMargins(40, 0, 40, 40)
        self._body_layout.setSpacing(0)

        # empty state
        self._empty_label = QLabel("Пока нет прохождений")
        self._empty_label.setFont(QFont(FONT_FAMILY, 16))
        self._empty_label.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.hide()
        self._body_layout.addWidget(self._empty_label)

        # ── statistics section (hidden until records load) ────────────────────
        self._stats_section = QWidget()
        self._stats_section.setStyleSheet("background: transparent;")
        stats_layout = QVBoxLayout(self._stats_section)
        stats_layout.setContentsMargins(0, 0, 0, 24)
        stats_layout.setSpacing(16)

        stats_title = QLabel("Статистика")
        stats_title.setFont(QFont(FONT_FAMILY, 20, QFont.Weight.Bold))
        stats_title.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")
        stats_layout.addWidget(stats_title)

        # summary row: counters + export button
        summary_row = QHBoxLayout()
        summary_row.setSpacing(24)

        self._passes_label = QLabel()
        self._passes_label.setFont(QFont(FONT_FAMILY, 14))
        self._passes_label.setStyleSheet(
            f"color: {TEXT_PRIMARY}; background-color: {CARD_BG};"
            f" border-radius: {CORNER_RADIUS}px; padding: 12px 20px;"
        )
        summary_row.addWidget(self._passes_label)

        self._users_label = QLabel()
        self._users_label.setFont(QFont(FONT_FAMILY, 14))
        self._users_label.setStyleSheet(
            f"color: {TEXT_PRIMARY}; background-color: {CARD_BG};"
            f" border-radius: {CORNER_RADIUS}px; padding: 12px 20px;"
        )
        summary_row.addWidget(self._users_label)

        summary_row.addStretch()

        export_btn = QPushButton("Экспорт в CSV")
        export_btn.setFont(QFont(FONT_FAMILY, 13))
        export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        export_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {BUTTON_BG};
                color: white;
                border: none;
                border-radius: {CORNER_RADIUS}px;
                padding: 10px 20px;
            }}
            QPushButton:hover {{ background-color: {BUTTON_HOVER}; }}
        """)
        export_btn.clicked.connect(self._on_export_csv)
        summary_row.addWidget(export_btn)

        stats_layout.addLayout(summary_row)

        # pie charts row
        pie_header = QLabel("Статистика попаданий по зонам интереса")
        pie_header.setFont(QFont(FONT_FAMILY, 14))
        pie_header.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")
        self._pie_header = pie_header
        stats_layout.addWidget(pie_header)

        self._pie_row = QHBoxLayout()
        self._pie_row.setSpacing(16)
        self._pie_row.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._pie_container = QWidget()
        self._pie_container.setStyleSheet("background: transparent;")
        self._pie_container.setLayout(self._pie_row)
        stats_layout.addWidget(self._pie_container)

        self._no_roi_label = QLabel("Нет данных по зонам интереса")
        self._no_roi_label.setFont(QFont(FONT_FAMILY, 13))
        self._no_roi_label.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")
        self._no_roi_label.hide()
        stats_layout.addWidget(self._no_roi_label)

        self._stats_section.hide()
        self._body_layout.addWidget(self._stats_section)

        # ── separator ─────────────────────────────────────────────────────────
        self._separator = QWidget()
        self._separator.setFixedHeight(1)
        self._separator.setStyleSheet(f"background-color: {BORDER_COLOR};")
        self._separator.hide()
        self._body_layout.addWidget(self._separator)

        # ── passes table title ────────────────────────────────────────────────
        self._table_title = QLabel("Прохождения")
        self._table_title.setFont(QFont(FONT_FAMILY, 20, QFont.Weight.Bold))
        self._table_title.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent; padding-top: 24px; padding-bottom: 12px;")
        self._table_title.hide()
        self._body_layout.addWidget(self._table_title)

        # ── filter bar ────────────────────────────────────────────────────────
        _dt_active_style = f"""
            QDateTimeEdit {{
                background-color: {CARD_BG};
                color: {TEXT_PRIMARY};
                border: 1px solid {BUTTON_BG};
                border-radius: {CORNER_RADIUS}px;
                padding: 6px 10px;
                font-family: {FONT_FAMILY};
                font-size: 13px;
            }}
            QDateTimeEdit::up-button, QDateTimeEdit::down-button {{ width: 0; border: none; }}
            QDateTimeEdit::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 24px;
                border: none;
            }}
        """
        _dt_inactive_style = f"""
            QDateTimeEdit {{
                background-color: {CARD_BG};
                color: {TEXT_SECONDARY};
                border: 1px solid {BORDER_COLOR};
                border-radius: {CORNER_RADIUS}px;
                padding: 6px 10px;
                font-family: {FONT_FAMILY};
                font-size: 13px;
            }}
            QDateTimeEdit::up-button, QDateTimeEdit::down-button {{ width: 0; border: none; }}
            QDateTimeEdit::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 24px;
                border: none;
            }}
        """
        _calendar_style = f"""
            QCalendarWidget QWidget {{ background-color: {BG_SIDEBAR}; color: {TEXT_PRIMARY}; }}
            QCalendarWidget QAbstractItemView {{
                background-color: {BG_SIDEBAR};
                color: {TEXT_PRIMARY};
                selection-background-color: {BUTTON_BG};
                selection-color: white;
                gridline-color: {BORDER_COLOR};
                outline: none;
            }}
            QCalendarWidget QAbstractItemView:disabled {{ color: #555; }}
            QCalendarWidget QWidget#qt_calendar_navigationbar {{
                background-color: {BG_MAIN};
                padding: 4px;
            }}
            QCalendarWidget QToolButton {{
                color: {TEXT_PRIMARY};
                background-color: transparent;
                font-family: {FONT_FAMILY};
                font-size: 13px;
                padding: 4px 8px;
                border: none;
                border-radius: {CORNER_RADIUS}px;
            }}
            QCalendarWidget QToolButton:hover {{ background-color: {BORDER_COLOR}; }}
            QCalendarWidget QToolButton::menu-indicator {{ width: 0; }}
            QCalendarWidget QSpinBox {{
                color: {TEXT_PRIMARY};
                background-color: {CARD_BG};
                border: 1px solid {BORDER_COLOR};
                border-radius: 4px;
                padding: 2px 6px;
                font-family: {FONT_FAMILY};
                font-size: 13px;
            }}
            QCalendarWidget QSpinBox::up-button, QCalendarWidget QSpinBox::down-button {{
                width: 16px;
            }}
        """
        _clear_btn_style = f"""
            QPushButton {{
                background-color: transparent;
                color: {TEXT_SECONDARY};
                border: none;
                font-size: 14px;
                padding: 0 4px;
            }}
            QPushButton:hover {{ color: {TEXT_PRIMARY}; }}
        """
        _combo_style = f"""
            QComboBox {{
                background-color: {CARD_BG};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER_COLOR};
                border-radius: {CORNER_RADIUS}px;
                padding: 6px 10px;
                font-family: {FONT_FAMILY};
                font-size: 12px;
                min-width: 110px;
            }}
            QComboBox::drop-down {{ border: none; width: 20px; }}
            QComboBox QAbstractItemView {{
                background-color: {CARD_BG};
                color: {TEXT_PRIMARY};
                selection-background-color: {BUTTON_BG};
                border: 1px solid {BORDER_COLOR};
            }}
        """

        self._dt_active_style = _dt_active_style
        self._dt_inactive_style = _dt_inactive_style
        self._filter_from_active = False
        self._filter_to_active = False

        self._filter_bar = QWidget()
        self._filter_bar.setStyleSheet("background: transparent;")
        filter_layout = QVBoxLayout(self._filter_bar)
        filter_layout.setContentsMargins(0, 0, 0, 12)
        filter_layout.setSpacing(8)

        # row 1: date-from / date-to / user / reset button
        row1 = QHBoxLayout()
        row1.setSpacing(8)

        from_lbl = QLabel("с:")
        from_lbl.setFont(QFont(FONT_FAMILY, 12))
        from_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")
        row1.addWidget(from_lbl)

        self._filter_from = QDateTimeEdit()
        self._filter_from.setDisplayFormat("dd.MM.yyyy HH:mm")
        self._filter_from.setDateTime(QDateTime.currentDateTime())
        self._filter_from.setCalendarPopup(True)
        self._filter_from.setFixedWidth(175)
        self._filter_from.setStyleSheet(_dt_inactive_style)
        self._filter_from.dateTimeChanged.connect(self._on_from_dt_changed)
        cal_from = self._filter_from.calendarWidget()
        cal_from.setStyleSheet(_calendar_style)
        row1.addWidget(self._filter_from)

        clear_from = QPushButton("×")
        clear_from.setFixedSize(22, 22)
        clear_from.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_from.setStyleSheet(_clear_btn_style)
        clear_from.clicked.connect(self._clear_from)
        row1.addWidget(clear_from)

        to_lbl = QLabel("по:")
        to_lbl.setFont(QFont(FONT_FAMILY, 12))
        to_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent; margin-left: 8px;")
        row1.addWidget(to_lbl)

        self._filter_to = QDateTimeEdit()
        self._filter_to.setDisplayFormat("dd.MM.yyyy HH:mm")
        self._filter_to.setDateTime(QDateTime.currentDateTime())
        self._filter_to.setCalendarPopup(True)
        self._filter_to.setFixedWidth(175)
        self._filter_to.setStyleSheet(_dt_inactive_style)
        self._filter_to.dateTimeChanged.connect(self._on_to_dt_changed)
        cal_to = self._filter_to.calendarWidget()
        cal_to.setStyleSheet(_calendar_style)
        row1.addWidget(self._filter_to)

        clear_to = QPushButton("×")
        clear_to.setFixedSize(22, 22)
        clear_to.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_to.setStyleSheet(_clear_btn_style)
        clear_to.clicked.connect(self._clear_to)
        row1.addWidget(clear_to)

        user_lbl = QLabel("пользователь:")
        user_lbl.setFont(QFont(FONT_FAMILY, 12))
        user_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent; margin-left: 8px;")
        row1.addWidget(user_lbl)

        self._filter_user_combo = QComboBox()
        self._filter_user_combo.addItem("Все")
        self._filter_user_combo.setFixedWidth(180)
        self._filter_user_combo.setStyleSheet(_combo_style)
        self._filter_user_combo.currentIndexChanged.connect(self._apply_filters)
        row1.addWidget(self._filter_user_combo)

        row1.addStretch()

        reset_btn = QPushButton("Сбросить")
        reset_btn.setFont(QFont(FONT_FAMILY, 12))
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {BUTTON_BG};
                border: 1px solid {BUTTON_BG};
                border-radius: {CORNER_RADIUS}px;
                padding: 6px 14px;
            }}
            QPushButton:hover {{ background-color: {BUTTON_BG}; color: white; }}
        """)
        reset_btn.clicked.connect(self._reset_filters)
        row1.addWidget(reset_btn)

        filter_layout.addLayout(row1)

        # row 2: per-ROI combos (built dynamically in _load_records)
        self._roi_filter_row = QHBoxLayout()
        self._roi_filter_row.setSpacing(10)
        self._roi_filter_row.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._roi_filter_row_widget = QWidget()
        self._roi_filter_row_widget.setStyleSheet("background: transparent;")
        self._roi_filter_row_widget.setLayout(self._roi_filter_row)
        self._roi_filter_row_widget.hide()
        filter_layout.addWidget(self._roi_filter_row_widget)

        self._combo_style = _combo_style

        self._filter_bar.hide()
        self._body_layout.addWidget(self._filter_bar)

        # ── table ─────────────────────────────────────────────────────────────
        self._table = QTableWidget()
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {BG_SIDEBAR};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER_COLOR};
                border-radius: {CORNER_RADIUS}px;
                gridline-color: {BORDER_COLOR};
            }}
            QTableWidget::item {{
                padding: 14px 12px;
            }}
            QHeaderView::section {{
                background-color: {BG_MAIN};
                color: {TEXT_SECONDARY};
                border: none;
                border-bottom: 1px solid {BORDER_COLOR};
                padding: 10px 12px;
                font-weight: bold;
            }}
        """)
        self._table.cellClicked.connect(self._on_cell_clicked)
        self._table.setCursor(Qt.CursorShape.PointingHandCursor)
        self._body_layout.addWidget(self._table)
        self._body_layout.addStretch(1)

        scroll.setWidget(body)
        outer.addWidget(scroll, stretch=1)

    def _load_records(self) -> None:
        result = self._record_service.query(RecordQuery(test_id=self._test_id, page_size=10_000))
        self._all_summaries = result.items

        if not self._all_summaries:
            self._empty_label.show()
            self._table.hide()
            self._filter_bar.hide()
            self._stats_section.hide()
            self._separator.hide()
            self._table_title.hide()
            return

        self._empty_label.hide()
        self._table.show()
        self._filter_bar.show()
        self._stats_section.show()
        self._separator.show()
        self._table_title.show()

        # ── summary stats (no record loads needed) ────────────────────────────
        self._passes_label.setText(f"Прохождений: {len(self._all_summaries)}")
        self._users_label.setText(f"Уникальных пользователей: {len({s.user_login for s in self._all_summaries})}")

        # ── pie charts via single roi-stats request ───────────────────────────
        roi_stats = self._record_service.get_roi_stats(self._test_id)

        while self._pie_row.count():
            item = self._pie_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if roi_stats:
            self._pie_header.show()
            self._pie_container.show()
            self._no_roi_label.hide()
            for idx, stat in enumerate(roi_stats):
                color = stat.color or _ROI_COLORS[idx % len(_ROI_COLORS)]
                chart = _PieChartWidget(stat.name, stat.hits, stat.total, color, first_fixation_required=stat.first_fixation_required)
                self._pie_row.addWidget(chart)
        else:
            self._pie_header.hide()
            self._pie_container.hide()
            self._no_roi_label.show()

        # ── build ROI filter combos ───────────────────────────────────────────
        while self._roi_filter_row.count():
            it = self._roi_filter_row.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self._roi_filter_combos.clear()

        roi_names = [s.name for s in roi_stats]
        self._roi_names = roi_names
        self._setup_table_columns()
        if roi_names:
            roi_lbl = QLabel("Зоны интереса:")
            roi_lbl.setFont(QFont(FONT_FAMILY, 12))
            roi_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")
            self._roi_filter_row.addWidget(roi_lbl)

            for name in roi_names:
                lbl = QLabel(name)
                lbl.setFont(QFont(FONT_FAMILY, 12))
                lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")
                self._roi_filter_row.addWidget(lbl)

                combo = QComboBox()
                combo.addItems(["Все", "Попадание", "Промах"])
                combo.setStyleSheet(self._combo_style)
                combo.currentIndexChanged.connect(self._on_non_user_filter_changed)
                self._roi_filter_row.addWidget(combo)
                self._roi_filter_combos[name] = combo

            self._roi_filter_row_widget.show()
        else:
            self._roi_filter_row_widget.hide()

        # ── render table rows ─────────────────────────────────────────────────
        self._refresh_user_combo()
        self._apply_filters()

        # ── ROI sync check ────────────────────────────────────────────────────
        if (
            self._test_dao is not None
            and self._test is not None
            and self._record_service.is_roi_sync_needed(self._test.id, self._test.image_regions)
        ):
            self._sync_btn.setEnabled(True)
            self._sync_btn.setText("Синхронизировать зоны интереса")
            self._sync_label.setText(
                "Некоторые записи содержат устаревшие данные зон интереса — "
                "зоны были добавлены или удалены после проведения тестов."
            )
            self._sync_banner.show()

    def _on_from_dt_changed(self) -> None:
        if not self._filter_from_active:
            self._filter_from_active = True
            self._filter_from.setStyleSheet(self._dt_active_style)
        self._on_non_user_filter_changed()

    def _on_to_dt_changed(self) -> None:
        if not self._filter_to_active:
            self._filter_to_active = True
            self._filter_to.setStyleSheet(self._dt_active_style)
        self._on_non_user_filter_changed()

    def _clear_from(self) -> None:
        self._filter_from_active = False
        self._filter_from.blockSignals(True)
        self._filter_from.setDateTime(QDateTime.currentDateTime())
        self._filter_from.blockSignals(False)
        self._filter_from.setStyleSheet(self._dt_inactive_style)
        self._on_non_user_filter_changed()

    def _clear_to(self) -> None:
        self._filter_to_active = False
        self._filter_to.blockSignals(True)
        self._filter_to.setDateTime(QDateTime.currentDateTime())
        self._filter_to.blockSignals(False)
        self._filter_to.setStyleSheet(self._dt_inactive_style)
        self._on_non_user_filter_changed()

    def _setup_table_columns(self) -> None:
        n_roi = len(self._roi_names)
        total = 3 + n_roi
        self._table.setColumnCount(total)
        labels = ["Дата и время", "Пользователь"] + self._roi_names + ["Управление"]
        self._table.setHorizontalHeaderLabels(labels)
        hdr = self._table.horizontalHeader()
        for i in range(total - 1):
            hdr.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(total - 1, QHeaderView.ResizeMode.Stretch)
        self._table.setColumnWidth(0, 155)
        self._table.setColumnWidth(1, 120)
        for i in range(n_roi):
            self._table.setColumnWidth(2 + i, 100)

    def _on_non_user_filter_changed(self) -> None:
        self._refresh_user_combo()
        self._apply_filters()

    def _refresh_user_combo(self) -> None:
        current = self._filter_user_combo.currentText()
        params = self._build_base_query()
        users = self._record_service.suggest_users(params)
        self._filter_user_combo.blockSignals(True)
        self._filter_user_combo.clear()
        self._filter_user_combo.addItem("Все")
        self._filter_user_combo.addItems(users)
        idx = self._filter_user_combo.findText(current)
        self._filter_user_combo.setCurrentIndex(max(0, idx))
        self._filter_user_combo.blockSignals(False)

    def _build_base_query(self) -> RecordQuery:
        """Build query from current non-user filter state."""
        date_from: str | None = None
        date_to: str | None = None
        if self._filter_from_active:
            date_from = self._filter_from.dateTime().toPyDateTime().isoformat()
        if self._filter_to_active:
            date_to = self._filter_to.dateTime().toPyDateTime().isoformat()
        roi_hits: dict[str, bool] | None = None
        active_roi = {
            name: combo.currentIndex()
            for name, combo in self._roi_filter_combos.items()
            if combo.currentIndex() != 0
        }
        if active_roi:
            roi_hits = {name: (idx == 1) for name, idx in active_roi.items()}
        return RecordQuery(
            test_id=self._test_id,
            date_from=date_from,
            date_to=date_to,
            roi_hits=roi_hits,
            page_size=10_000,
        )

    def _apply_filters(self) -> None:
        # ROI filter — server-side (only query when active)
        active_roi = {
            name: combo.currentIndex()
            for name, combo in self._roi_filter_combos.items()
            if combo.currentIndex() != 0
        }
        if active_roi:
            query = self._build_base_query()
            query.roi_hits = {name: (idx == 1) for name, idx in active_roi.items()}
            filtered = self._record_service.query(query).items
        else:
            filtered = list(self._all_summaries)

        # User filter — client-side
        if self._filter_user_combo.currentIndex() > 0:
            selected_user = self._filter_user_combo.currentText()
            filtered = [s for s in filtered if s.user_login == selected_user]

        # Date filters — client-side (ISO 8601 strings are lexicographically comparable)
        if self._filter_from_active:
            date_from = self._filter_from.dateTime().toPyDateTime().isoformat()
            filtered = [s for s in filtered if s.started_at >= date_from]
        if self._filter_to_active:
            date_to = self._filter_to.dateTime().toPyDateTime().isoformat()
            filtered = [s for s in filtered if s.started_at <= date_to]

        self._filtered_summaries = filtered

        n_roi = len(self._roi_names)
        col_mgmt = 2 + n_roi

        self._table.setRowCount(len(filtered))
        for row, summary in enumerate(filtered):
            dt_item = QTableWidgetItem(format_datetime(summary.started_at))
            dt_item.setFont(QFont(FONT_FAMILY, 13))
            self._table.setItem(row, 0, dt_item)

            login_item = QTableWidgetItem(summary.user_login)
            login_item.setFont(QFont(FONT_FAMILY, 13))
            self._table.setItem(row, 1, login_item)

            hit_map: dict[str, bool] = {}
            for r in summary.roi_hits:
                raw_name = r["name"]
                hit = bool(r.get("hit", False))
                # index by full name
                hit_map[raw_name] = hit_map.get(raw_name, False) or hit
                # also index by base name without " (N)" suffix
                if " (" in raw_name:
                    base = raw_name.rsplit(" (", 1)[0]
                    hit_map[base] = hit_map.get(base, False) or hit
            for i, name in enumerate(self._roi_names):
                hit = hit_map.get(name)
                if hit is None:
                    text, color = "—", TEXT_SECONDARY
                elif hit:
                    text, color = "✓", "#30d158"
                else:
                    text, color = "✗", "#ff453a"
                roi_item = QTableWidgetItem(text)
                roi_item.setFont(QFont(FONT_FAMILY, 14))
                roi_item.setForeground(QColor(color))
                roi_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row, 2 + i, roi_item)

            self._table.setCellWidget(row, col_mgmt, self._make_mgmt_widget(summary.id))

        self._table.resizeRowsToContents()
        self._fit_table_height()

    def _make_mgmt_widget(self, record_id: str) -> QWidget:
        _btn_style = f"""
            QPushButton {{
                background: transparent;
                color: {BUTTON_BG};
                border: none;
                font-family: {FONT_FAMILY};
                font-size: 13px;
                padding: 4px 8px;
            }}
            QPushButton:hover {{ color: {BUTTON_HOVER}; }}
        """
        container = QWidget()
        container.setStyleSheet(f"background: transparent;")
        layout = QHBoxLayout(container)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(4)

        report_btn = QPushButton("Отчёт")
        report_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        report_btn.setStyleSheet(_btn_style)
        report_btn.clicked.connect(lambda _, rid=record_id: self._on_view_report(rid))
        layout.addWidget(report_btn)

        sep = QLabel("|")
        sep.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")
        layout.addWidget(sep)

        export_btn = QPushButton("Экспорт")
        export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        export_btn.setStyleSheet(_btn_style)
        export_btn.clicked.connect(lambda _, rid=record_id: self._export_record(rid))
        layout.addWidget(export_btn)

        layout.addStretch()
        return container

    def _fit_table_height(self) -> None:
        h = self._table.horizontalHeader().height()
        for i in range(self._table.rowCount()):
            h += self._table.rowHeight(i)
        self._table.setFixedHeight(h + 2)

    def _on_cell_clicked(self, row: int, col: int) -> None:
        pass

    def _reset_filters(self) -> None:
        self._clear_from()
        self._clear_to()
        for combo in self._roi_filter_combos.values():
            combo.setCurrentIndex(0)
        self._filter_user_combo.setCurrentIndex(0)

    @staticmethod
    def _safe(s: str) -> str:
        return "".join(c if c.isalnum() or c in "-_" else "_" for c in s)

    def _export_record(self, record_id: str) -> None:
        record = self._record_service.load(record_id)
        if record is None:
            return
        dt_part = record.started_at[:19].replace("T", "_").replace(":", "-")
        suggested = f"{self._safe(self._test_name)}_{dt_part}_{self._safe(record.user_login)}.zip"
        path, _ = QFileDialog.getSaveFileName(
            self, "Экспорт записи", suggested, "ZIP архив (*.zip)"
        )
        if not path:
            return
        try:
            export_record_zip(record, Path(path), self._test_dao, self._test)
        except Exception as exc:
            msg = QMessageBox(self)
            msg.setWindowTitle("Ошибка экспорта")
            msg.setText(str(exc))
            msg.exec()

    def _on_export_csv(self) -> None:
        base = self._safe(self._test_name)
        zip_path, _ = QFileDialog.getSaveFileName(
            self, "Экспорт в CSV", f"{base}_statistics.zip", "ZIP архив (*.zip)"
        )
        if not zip_path:
            return

        metric_cols = [
            "Кол-во фиксаций",
            "Кол-во саккад",
            "Центры фиксаций (JSON)",
            "Начало/конец саккад (JSON)",
            "Первая точка фиксации",
        ]

        per_image_headers = (
            ["Дата и время", "Пользователь", "Изображение"]
            + self._roi_names
            + metric_cols
        )
        roi_defs_headers = ["Изображение"] + self._roi_names

        per_image_rows: list[list] = []

        for summary in self._all_summaries:
            rec = self._record_service.load(summary.id)
            dt = format_datetime(summary.started_at)

            if rec:
                for item in rec.items:
                    img_roi_hit: dict[str, bool] = {}
                    for roi in item.metrics.roi_metrics:
                        img_roi_hit[roi.get("name", "")] = bool(roi.get("hit"))

                    img_fix_centers: list[dict] = []
                    img_first_fix: dict | None = None
                    for fx in item.metrics.fixations:
                        center = fx.get("center", {})
                        pt = {"x": center.get("x"), "y": center.get("y")}
                        img_fix_centers.append(pt)
                        if fx.get("is_first") and img_first_fix is None:
                            img_first_fix = pt

                    img_sac_endpoints: list[dict] = []
                    for sc in item.metrics.saccades:
                        pts = sc.get("points", [])
                        if pts:
                            img_sac_endpoints.append({
                                "start": {"x": pts[0]["x"], "y": pts[0]["y"]},
                                "end": {"x": pts[-1]["x"], "y": pts[-1]["y"]},
                            })

                    img_row: list = [dt, summary.user_login, item.image_filename]
                    for roi_name in self._roi_names:
                        img_row.append("✓" if img_roi_hit.get(roi_name) else "")
                    img_row.extend([
                        len(item.metrics.fixations),
                        len(item.metrics.saccades),
                        json.dumps(img_fix_centers, ensure_ascii=False),
                        json.dumps(img_sac_endpoints, ensure_ascii=False),
                        json.dumps(img_first_fix, ensure_ascii=False) if img_first_fix is not None else "",
                    ])
                    per_image_rows.append(img_row)

        # ── ROI definitions from test settings ────────────────────────────────
        roi_defs_rows: list[list] = []
        if self._test is not None:
            for filename in self._test.image_filenames:
                defined = {
                    r["name"]
                    for r in self._test.image_regions.get(filename, [])
                    if "name" in r
                }
                row: list = [filename]
                for roi_name in self._roi_names:
                    row.append("TRUE" if roi_name in defined else "FALSE")
                roi_defs_rows.append(row)

        def _csv_bytes(headers: list, rows: list[list]) -> bytes:
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(headers)
            writer.writerows(rows)
            return ("\ufeff" + buf.getvalue()).encode("utf-8")

        # ── README from template file ─────────────────────────────────────────
        roi_list = ", ".join(f"`{r}`" for r in self._roi_names) or "_(нет зон интереса)_"
        readme_template_path = _RESOURCES_DIR / "csv_export_readme.md"
        try:
            readme_template = readme_template_path.read_text(encoding="utf-8")
        except OSError:
            readme_template = ""
        readme = readme_template.format(
            test_name=self._test_name,
            roi_list=roi_list,
            per_image_csv=f"{base}_per_image.csv",
            roi_defs_csv=f"{base}_roi_definitions.csv",
        )

        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("README.md", readme.encode("utf-8"))
                zf.writestr(f"{base}_per_image.csv", _csv_bytes(per_image_headers, per_image_rows))
                zf.writestr(f"{base}_roi_definitions.csv", _csv_bytes(roi_defs_headers, roi_defs_rows))
        except OSError as exc:
            msg = QMessageBox(self)
            msg.setWindowTitle("Ошибка экспорта")
            msg.setText(str(exc))
            msg.exec()

    def _on_sync_clicked(self) -> None:
        if self._test_dao is None or self._test is None:
            return
        self._sync_btn.setEnabled(False)
        self._sync_btn.setText("Синхронизация зон интереса…")
        self._sync_label.setText("Пересчёт ROI для всех записей…")

        def _run() -> None:
            try:
                self._test_dao.sync_roi_metrics(self._test_id, self._record_service)
                QTimer.singleShot(0, self._on_sync_done)
            except Exception as exc:
                msg = str(exc)
                QTimer.singleShot(0, lambda: self._on_sync_error(msg))

        threading.Thread(target=_run, daemon=True).start()

    def _on_sync_done(self) -> None:
        self._sync_banner.hide()
        self._load_records()

    def _on_sync_error(self, message: str) -> None:
        self._sync_btn.setEnabled(True)
        self._sync_btn.setText("Синхронизировать зоны интереса")
        self._sync_label.setText("Ошибка синхронизации — попробуйте ещё раз")
        QMessageBox.warning(self, "Ошибка синхронизации", message)
