"""Records list page: table of test run results."""

from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt, QThread, pyqtSignal
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
from eyetracker.data.test.dao import TestDao, TestData
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


class _SyncWorker(QThread):
    finished = pyqtSignal()

    def __init__(self, test_dao: TestDao, test_id: str, record_service: RecordService):
        super().__init__()
        self._test_dao = test_dao
        self._test_id = test_id
        self._record_service = record_service

    def run(self) -> None:
        self._test_dao.sync_roi_metrics(self._test_id, self._record_service)
        self.finished.emit()


def _roi_sync_needed(test: TestData, record_service: RecordService) -> bool:
    """Return True if any record for this test has ROI metrics that don't match
    the test's current image_regions (added or removed ROIs)."""
    result = record_service.query(RecordQuery(test_id=test.id, page_size=10_000))
    for summary in result.items:
        record = record_service.load(summary.id)
        if record is None:
            continue
        for item in record.items:
            current_rois = test.image_regions.get(item.image_filename, [])
            current_names = {r["name"] for r in current_rois}
            record_names = {r["name"] for r in item.metrics.roi_metrics}
            if current_names != record_names:
                return True
    return False


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
        self._sync_worker: _SyncWorker | None = None

        self.setStyleSheet(f"background-color: {BG_MAIN};")
        self._build_ui()
        self._load_records()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

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

        layout.addWidget(header)

        # ── body (empty label OR table) ───────────────────────────────────────
        self._empty_label = QLabel("Пока нет прохождений")
        self._empty_label.setFont(QFont(FONT_FAMILY, 16))
        self._empty_label.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.hide()
        layout.addWidget(self._empty_label, stretch=1)

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
        self._table.setContentsMargins(40, 0, 40, 40)
        self._table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {BG_SIDEBAR};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER_COLOR};
                border-radius: {CORNER_RADIUS}px;
                gridline-color: {BORDER_COLOR};
                margin: 0 40px 40px 40px;
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

        # Check if ROI sync is needed
        if self._test_dao is not None and self._test is not None:
            if _roi_sync_needed(self._test, self._record_service):
                self._sync_banner.show()

    def _on_sync_clicked(self) -> None:
        if self._test_dao is None or self._test is None:
            return
        self._sync_btn.setEnabled(False)
        self._sync_btn.setText("Синхронизация зон интереса…")
        self._sync_label.setText("Пересчёт ROI для всех записей…")

        self._sync_worker = _SyncWorker(self._test_dao, self._test_id, self._record_service)
        self._sync_worker.finished.connect(self._on_sync_done)
        self._sync_worker.start()

    def _on_sync_done(self) -> None:
        self._sync_banner.hide()
        # Refresh table so "view report" buttons still work
        self._load_records()
