"""Records list page: table of test run results."""

from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from eyetracker.core.time_fmt import format_datetime
from eyetracker.data.record.service import RecordQuery, RecordService
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


class RecordsListPage(QWidget):
    """Table of record summaries for a given test."""

    def __init__(
        self,
        record_service: RecordService,
        test_id: str,
        test_name: str,
        on_view_report: Callable[[str], None],
        on_back: Callable[[], None],
    ):
        super().__init__()
        self._record_service = record_service
        self._test_id = test_id
        self._test_name = test_name
        self._on_view_report = on_view_report
        self._on_back = on_back

        self.setStyleSheet(f"background-color: {BG_MAIN};")
        self._build_ui()
        self._load_records()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(16)

        # Header row
        header_row = QHBoxLayout()
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
        header_row.addWidget(back_btn)
        header_row.addStretch()
        layout.addLayout(header_row)

        title = QLabel(f"Результаты: {self._test_name}")
        title.setFont(QFont(FONT_FAMILY, 28, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")
        layout.addWidget(title)

        # Empty state label
        self._empty_label = QLabel("Пока нет прохождений")
        self._empty_label.setFont(QFont(FONT_FAMILY, 16))
        self._empty_label.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.hide()
        layout.addWidget(self._empty_label)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(3)
        self._table.setHorizontalHeaderLabels(["Дата и время", "Пользователь", ""])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {BG_SIDEBAR};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER_COLOR};
                border-radius: {CORNER_RADIUS}px;
                gridline-color: {BORDER_COLOR};
            }}
            QTableWidget::item {{
                padding: 8px;
            }}
            QHeaderView::section {{
                background-color: {BG_MAIN};
                color: {TEXT_SECONDARY};
                border: none;
                border-bottom: 1px solid {BORDER_COLOR};
                padding: 8px;
                font-weight: bold;
            }}
        """)
        layout.addWidget(self._table, stretch=1)

    def _load_records(self) -> None:
        result = self._record_service.query(RecordQuery(test_id=self._test_id))
        summaries = result.items

        if not summaries:
            self._empty_label.show()
            self._table.hide()
            return

        self._table.setRowCount(len(summaries))
        for row, summary in enumerate(summaries):
            dt_item = QTableWidgetItem(format_datetime(summary.started_at))
            dt_item.setFont(QFont(FONT_FAMILY, 13))
            self._table.setItem(row, 0, dt_item)

            login_item = QTableWidgetItem(summary.user_login)
            login_item.setFont(QFont(FONT_FAMILY, 13))
            self._table.setItem(row, 1, login_item)

            view_btn = QPushButton("Посмотреть отчет")
            view_btn.setFont(QFont(FONT_FAMILY, 12))
            view_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            view_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {BUTTON_BG};
                    color: white;
                    border: none;
                    border-radius: {CORNER_RADIUS}px;
                    padding: 6px 14px;
                }}
                QPushButton:hover {{
                    background-color: {BUTTON_HOVER};
                }}
            """)
            view_btn.clicked.connect(lambda checked, rid=summary.id: self._on_view_report(rid))
            self._table.setCellWidget(row, 2, view_btn)

        self._table.resizeRowsToContents()
