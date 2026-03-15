"""Home screen with sidebar and content area."""

from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QKeyEvent
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from eyetracker.create_test_form import CreateTestFormPage
from eyetracker.create_test_page import CreateTestChoicePage
from eyetracker.monitor import format_screen_label, get_available_screens
from eyetracker.settings import Settings
from eyetracker.test_dao import TestDao
from eyetracker.theme import (
    BG_MAIN,
    BG_SIDEBAR,
    BG_SIDEBAR_ACTIVE,
    BG_SIDEBAR_HOVER,
    BORDER_COLOR,
    BUTTON_BG,
    BUTTON_HOVER,
    CORNER_RADIUS,
    FONT_FAMILY,
    SIDEBAR_ITEM_HEIGHT,
    SIDEBAR_PADDING,
    SIDEBAR_WIDTH,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

_SIDEBAR_ITEMS = [
    {"id": "overview", "title": "Обзор", "icon": "⌂"},
    {"id": "devices", "title": "Устройства", "icon": "⎚"},
    {"id": "calibration", "title": "Калибровка", "icon": "◎"},
    {"id": "create_test", "title": "Создать тест", "icon": "+"},
    {"id": "settings", "title": "Настройки", "icon": "⚙"},
    {"id": "help", "title": "Помощь", "icon": "?"},
]


class HomeScreen(QWidget):
    """Home screen with a macOS-style sidebar and content area."""

    def __init__(
        self,
        on_start_calibration: Callable[[], None],
        settings: Settings,
        test_dao: TestDao,
        on_monitor_changed: Callable[[], None] | None = None,
    ):
        super().__init__()
        self._on_start = on_start_calibration
        self._settings = settings
        self._on_monitor_changed_cb = on_monitor_changed
        self._test_dao = test_dao
        self._create_test_form: CreateTestFormPage | None = None
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_sidebar())

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFixedWidth(1)
        sep.setStyleSheet(f"background-color: {BORDER_COLOR};")
        layout.addWidget(sep)

        self._content_stack = QStackedWidget()
        self._content_stack.setStyleSheet(f"background-color: {BG_MAIN};")
        self._content_pages: dict[str, QWidget] = {}
        for item in _SIDEBAR_ITEMS:
            page = self._build_page(item["id"], item["title"])
            self._content_pages[item["id"]] = page
            self._content_stack.addWidget(page)
        self._content_stack.setCurrentWidget(self._content_pages["overview"])
        layout.addWidget(self._content_stack, stretch=1)

    # ---- Sidebar -------------------------------------------------------------

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setFixedWidth(SIDEBAR_WIDTH)
        sidebar.setStyleSheet(f"background-color: {BG_SIDEBAR};")

        vbox = QVBoxLayout(sidebar)
        vbox.setContentsMargins(SIDEBAR_PADDING, SIDEBAR_PADDING, SIDEBAR_PADDING, SIDEBAR_PADDING)
        vbox.setSpacing(4)

        self._btn_group = QButtonGroup(self)
        self._btn_group.setExclusive(True)

        for item in _SIDEBAR_ITEMS:
            btn = QPushButton(f"  {item['icon']}   {item['title']}")
            btn.setFixedHeight(SIDEBAR_ITEM_HEIGHT)
            btn.setCheckable(True)
            btn.setFlat(True)
            btn.setFont(QFont(FONT_FAMILY, 13))
            btn.setStyleSheet(f"""
                QPushButton {{
                    color: {TEXT_PRIMARY};
                    text-align: left;
                    padding-left: 12px;
                    border: none;
                    border-radius: {CORNER_RADIUS}px;
                    background-color: transparent;
                }}
                QPushButton:hover {{
                    background-color: {BG_SIDEBAR_HOVER};
                }}
                QPushButton:checked {{
                    background-color: {BG_SIDEBAR_ACTIVE};
                    color: white;
                }}
            """)
            btn.clicked.connect(lambda checked, iid=item["id"]: self._on_sidebar_click(iid))
            self._btn_group.addButton(btn)
            vbox.addWidget(btn)

            if item["id"] == "overview":
                btn.setChecked(True)

        vbox.addStretch()
        return sidebar

    def _on_sidebar_click(self, item_id: str):
        if item_id == "settings":
            self._refresh_monitor_combo()
        page = self._content_pages.get(item_id)
        if page:
            self._content_stack.setCurrentWidget(page)

    # ---- Content pages -------------------------------------------------------

    def _build_page(self, item_id: str, title: str) -> QWidget:
        if item_id == "overview":
            return self._build_overview_page()
        if item_id == "calibration":
            return self._build_calibration_page()
        if item_id == "create_test":
            return self._build_create_test_page()
        if item_id == "settings":
            return self._build_settings_page()
        return self._build_placeholder_page(title)

    def _build_overview_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet(f"background-color: {BG_MAIN};")

        vbox = QVBoxLayout(page)
        vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("EyeTracker")
        title.setFont(QFont(FONT_FAMILY, 36, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        desc = QLabel("Система отслеживания взгляда\nчерез веб-камеру")
        desc.setFont(QFont(FONT_FAMILY, 16))
        desc.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)

        vbox.addWidget(title)
        vbox.addSpacing(10)
        vbox.addWidget(desc)

        return page

    def _build_calibration_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet(f"background-color: {BG_MAIN};")

        vbox = QVBoxLayout(page)
        vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("Калибровка")
        title.setFont(QFont(FONT_FAMILY, 36, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        desc = QLabel(
            "Калибровка состоит из 9 точек на экране.\n"
            "Кликните по каждой точке 5 раз, глядя на неё.\n"
            "После калибровки будет измерена точность."
        )
        desc.setFont(QFont(FONT_FAMILY, 16))
        desc.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)

        btn = QPushButton("Начать калибровку")
        btn.setFixedSize(220, 44)
        btn.setFont(QFont(FONT_FAMILY, 15, QFont.Weight.Bold))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(self._on_start)
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

        vbox.addWidget(title)
        vbox.addSpacing(10)
        vbox.addWidget(desc)
        vbox.addSpacing(30)
        vbox.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)

        return page

    def _build_settings_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet(f"background-color: {BG_MAIN};")

        vbox = QVBoxLayout(page)
        vbox.setContentsMargins(40, 40, 40, 40)
        vbox.setAlignment(Qt.AlignmentFlag.AlignTop)

        title = QLabel("Настройки")
        title.setFont(QFont(FONT_FAMILY, 36, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")

        section_label = QLabel("Монитор для трекинга")
        section_label.setFont(QFont(FONT_FAMILY, 16))
        section_label.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")

        self._monitor_combo = QComboBox()
        self._monitor_combo.setFixedWidth(400)
        self._monitor_combo.setFont(QFont(FONT_FAMILY, 14))
        self._monitor_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {BG_SIDEBAR};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER_COLOR};
                border-radius: {CORNER_RADIUS}px;
                padding: 8px 12px;
            }}
            QComboBox::drop-down {{
                border: none;
            }}
            QComboBox QAbstractItemView {{
                background-color: {BG_SIDEBAR};
                color: {TEXT_PRIMARY};
                selection-background-color: {BG_SIDEBAR_ACTIVE};
            }}
        """)
        self._refresh_monitor_combo()
        self._monitor_combo.currentIndexChanged.connect(self._on_monitor_changed)

        vbox.addWidget(title)
        vbox.addSpacing(30)
        vbox.addWidget(section_label)
        vbox.addSpacing(8)
        vbox.addWidget(self._monitor_combo)
        vbox.addStretch()

        return page

    def _refresh_monitor_combo(self):
        """Rebuild the monitor combo box from currently available screens."""
        combo = self._monitor_combo
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("Основной монитор", userData=None)

        saved_name = self._settings.tracking_display_name
        selected_index = 0

        for i, screen in enumerate(get_available_screens()):
            label = format_screen_label(screen)
            combo.addItem(label, userData=screen.name())
            if screen.name() == saved_name:
                selected_index = i + 1

        combo.setCurrentIndex(selected_index)
        combo.blockSignals(False)

    def _on_monitor_changed(self, index: int):
        screen_name = self._monitor_combo.currentData()
        self._settings.tracking_display_name = screen_name
        if self._on_monitor_changed_cb:
            self._on_monitor_changed_cb()

    def _build_placeholder_page(self, title_text: str) -> QWidget:
        page = QWidget()
        page.setStyleSheet(f"background-color: {BG_MAIN};")

        vbox = QVBoxLayout(page)
        vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel(title_text)
        title.setFont(QFont(FONT_FAMILY, 36, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        desc = QLabel("Скоро здесь появится контент")
        desc.setFont(QFont(FONT_FAMILY, 16))
        desc.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)

        vbox.addWidget(title)
        vbox.addSpacing(10)
        vbox.addWidget(desc)

        return page

    # ---- Create test navigation -----------------------------------------------

    def _build_create_test_page(self) -> QWidget:
        page = CreateTestChoicePage()
        page.form_chosen.connect(self._show_create_test_form)
        return page

    def _show_create_test_form(self) -> None:
        if self._create_test_form is not None:
            self._content_stack.removeWidget(self._create_test_form)
            self._create_test_form.deleteLater()

        self._create_test_form = CreateTestFormPage(dao=self._test_dao)
        self._create_test_form.back_requested.connect(self._show_create_test_choice)
        self._create_test_form.test_created.connect(self._on_test_created)
        self._content_stack.addWidget(self._create_test_form)
        self._content_stack.setCurrentWidget(self._create_test_form)

    def _show_create_test_choice(self) -> None:
        if self._create_test_form is not None:
            self._content_stack.removeWidget(self._create_test_form)
            self._create_test_form.deleteLater()
            self._create_test_form = None
        page = self._content_pages.get("create_test")
        if page:
            self._content_stack.setCurrentWidget(page)

    def _on_test_created(self) -> None:
        self._show_create_test_choice()

    # ---- Keys ----------------------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent):  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            QApplication.quit()
