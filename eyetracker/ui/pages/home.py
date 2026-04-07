"""Home screen with sidebar and content area."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QFont, QKeyEvent, QPainter, QPainterPath, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QDoubleSpinBox,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from eyetracker.core.monitor import format_screen_label, get_available_screens
from eyetracker.data.draft_cache import DraftCache
from eyetracker.data.login import LoginService
from eyetracker.data.record.service import RecordService
from eyetracker.data.settings import Settings
from eyetracker.data.test import TestDao, TestData
from eyetracker.ui.pages.create_test_page import CreateTestChoicePage
from eyetracker.ui.pages.record_detail_page import RecordDetailPage
from eyetracker.ui.pages.records_list_page import RecordsListPage
from eyetracker.ui.pages.test_form_page import FormMode, TestFormPage
from eyetracker.ui.pages.test_library_page import TestLibraryPage
from eyetracker.ui.theme import (
    BG_MAIN,
    BG_SIDEBAR,
    BG_SIDEBAR_ACTIVE,
    BG_SIDEBAR_HOVER,
    BORDER_COLOR,
    BUTTON_BG,
    BUTTON_HOVER,
    CARD_BG,
    CARD_HOVER,
    CORNER_RADIUS,
    ERROR_COLOR,
    FONT_FAMILY,
    SIDEBAR_ITEM_HEIGHT,
    SIDEBAR_PADDING,
    SIDEBAR_WIDTH,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

_SIDEBAR_ITEMS = [
    {"id": "overview", "title": "Обзор", "icon": "⌂"},
    {"id": "calibration", "title": "Демо-трекер", "icon": "◎"},
    {"id": "tests", "title": "Тесты", "icon": "☰"},
    {"id": "create_test", "title": "Создать тест", "icon": "+"},
    {"id": "settings", "title": "Настройки", "icon": "⚙"},
    {"id": "help", "title": "Помощь", "icon": "?"},
]


class HomeScreen(QWidget):
    """Home screen with a macOS-style sidebar and content area."""

    def __init__(
        self,
        on_start_calibration: Callable[[], None],
        on_start_test_run: Callable[[TestData], None],
        settings: Settings,
        test_dao: TestDao,
        login_service: LoginService,
        draft_cache: DraftCache,
        record_service: RecordService,
        on_monitor_changed: Callable[[], None] | None = None,
    ):
        super().__init__()
        self._on_start = on_start_calibration
        self._on_start_test_run = on_start_test_run
        self._settings = settings
        self._on_monitor_changed_cb = on_monitor_changed
        self._test_dao = test_dao
        self._login_service = login_service
        self._draft_cache = draft_cache
        self._record_service = record_service
        self._readiness_page: QWidget | None = None
        self._readiness_test_id: str | None = None
        self._records_page: QWidget | None = None
        self._record_detail_page: QWidget | None = None
        self._detail_page: TestFormPage | None = None
        self._current_tab_id = "overview"
        self._sidebar_buttons: dict[str, QPushButton] = {}
        self._logged_in = self._settings.auth_token is not None
        self._current_username: str = self._settings.current_username
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

        self._update_auth_state(self._logged_in)
        if self._logged_in and self._draft_cache.exists():
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, self._show_draft_recovery_dialog)

    # ---- Draft recovery ------------------------------------------------------

    def _show_draft_recovery_dialog(self) -> None:
        draft = self._draft_cache.load()
        if draft is None:
            return
        msg = QMessageBox(self)
        msg.setWindowTitle("Восстановление")
        msg.setText("Обнаружен незавершённый черновик. Хотите продолжить?")
        continue_btn = msg.addButton("Продолжить", QMessageBox.ButtonRole.AcceptRole)
        no_btn = msg.addButton("Нет", QMessageBox.ButtonRole.DestructiveRole)
        msg.addButton("Позже", QMessageBox.ButtonRole.RejectRole)
        msg.exec()

        clicked = msg.clickedButton()
        if clicked == continue_btn:
            if draft.draft_type == "edit" and draft.test_id:
                self._select_sidebar_item("tests")
                self._show_test_detail(draft.test_id, FormMode.EDIT)
            else:
                self._select_sidebar_item("create_test")
                self._show_create_test_form()
        elif clicked == no_btn:
            self._draft_cache.clear()

    # ---- Auth state ----------------------------------------------------------

    def _update_auth_state(self, logged_in: bool) -> None:
        self._logged_in = logged_in
        for item_id, btn in self._sidebar_buttons.items():
            btn.setVisible(item_id == "overview" or logged_in)
        if hasattr(self, "_admin_section"):
            self._admin_section.setVisible(self._is_super_admin())
        if logged_in:
            self._overview_stack.setCurrentWidget(self._dashboard_page)
            self._refresh_dashboard()
        else:
            self._overview_stack.setCurrentWidget(self._login_page)
            if self._current_tab_id != "overview":
                self._select_sidebar_item("overview")

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
            self._sidebar_buttons[item["id"]] = btn
            vbox.addWidget(btn)

            if item["id"] == "overview":
                btn.setChecked(True)

        vbox.addStretch()
        return sidebar

    def _on_sidebar_click(self, item_id: str):
        self._current_tab_id = item_id
        if item_id == "settings":
            self._refresh_monitor_combo()
        if item_id == "tests":
            page = self._content_pages.get("tests")
            if isinstance(page, TestLibraryPage):
                page.refresh()
        if item_id == "overview" and self._logged_in:
            self._refresh_dashboard()
        page = self._content_pages.get(item_id)
        if page:
            self._content_stack.setCurrentWidget(page)

    def _select_sidebar_item(self, item_id: str) -> None:
        btn = self._sidebar_buttons.get(item_id)
        if btn:
            btn.setChecked(True)
            self._on_sidebar_click(item_id)

    # ---- Content pages -------------------------------------------------------

    def _build_page(self, item_id: str, title: str) -> QWidget:
        if item_id == "overview":
            return self._build_overview_page()
        if item_id == "calibration":
            return self._build_calibration_page()
        if item_id == "tests":
            return self._build_tests_page()
        if item_id == "create_test":
            return self._build_create_test_page()
        if item_id == "settings":
            return self._build_settings_page()
        if item_id == "help":
            return self._build_help_page()
        return self._build_placeholder_page(title)

    # ---- Overview page (login form + dashboard) ------------------------------

    def _build_overview_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet(f"background-color: {BG_MAIN};")

        self._overview_stack = QStackedWidget()
        self._login_page = self._build_login_form()
        self._dashboard_page = self._build_dashboard()
        self._overview_stack.addWidget(self._login_page)
        self._overview_stack.addWidget(self._dashboard_page)

        vbox = QVBoxLayout(page)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.addWidget(self._overview_stack)

        return page

    def _build_login_form(self) -> QWidget:
        self._form_mode = "login"  # "login" | "register"

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

        input_style = f"""
            QLineEdit {{
                background-color: {BG_SIDEBAR};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER_COLOR};
                border-radius: {CORNER_RADIUS}px;
                padding: 10px 14px;
                font-size: 14px;
            }}
            QLineEdit:focus {{
                border: 1px solid {BUTTON_BG};
            }}
        """

        self._login_input = QLineEdit()
        self._login_input.setPlaceholderText("Логин")
        self._login_input.setFixedWidth(320)
        self._login_input.setFont(QFont(FONT_FAMILY, 14))
        self._login_input.setStyleSheet(input_style)

        self._password_input = QLineEdit()
        self._password_input.setPlaceholderText("Пароль")
        self._password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._password_input.setFixedWidth(320)
        self._password_input.setFont(QFont(FONT_FAMILY, 14))
        self._password_input.setStyleSheet(input_style)
        self._password_input.returnPressed.connect(self._on_submit_click)

        self._login_error = QLabel("")
        self._login_error.setFont(QFont(FONT_FAMILY, 12))
        self._login_error.setStyleSheet(f"color: {ERROR_COLOR}; background: transparent;")
        self._login_error.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._login_error.setFixedWidth(320)
        self._login_error.hide()

        self._login_btn = QPushButton("Войти")
        self._login_btn.setFixedSize(320, 44)
        self._login_btn.setFont(QFont(FONT_FAMILY, 15, QFont.Weight.Bold))
        self._login_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._login_btn.clicked.connect(self._on_submit_click)
        self._login_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {BUTTON_BG};
                color: white;
                border: none;
                border-radius: {CORNER_RADIUS}px;
            }}
            QPushButton:hover {{
                background-color: {BUTTON_HOVER};
            }}
            QPushButton:disabled {{
                background-color: {BG_SIDEBAR_HOVER};
                color: {TEXT_SECONDARY};
            }}
        """)

        self._toggle_form_btn = QPushButton("Нет аккаунта? Зарегистрироваться")
        self._toggle_form_btn.setFixedWidth(320)
        self._toggle_form_btn.setFont(QFont(FONT_FAMILY, 13))
        self._toggle_form_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_form_btn.setFlat(True)
        self._toggle_form_btn.setStyleSheet(
            f"color: {BUTTON_BG}; background: transparent; border: none;"
        )
        self._toggle_form_btn.clicked.connect(self._on_toggle_form_mode)

        vbox.addWidget(title)
        vbox.addSpacing(10)
        vbox.addWidget(desc)
        vbox.addSpacing(30)
        vbox.addWidget(self._login_input, alignment=Qt.AlignmentFlag.AlignCenter)
        vbox.addSpacing(10)
        vbox.addWidget(self._password_input, alignment=Qt.AlignmentFlag.AlignCenter)
        vbox.addSpacing(6)
        vbox.addWidget(self._login_error, alignment=Qt.AlignmentFlag.AlignCenter)
        vbox.addSpacing(10)
        vbox.addWidget(self._login_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        vbox.addSpacing(8)
        vbox.addWidget(self._toggle_form_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        return page

    def _on_toggle_form_mode(self) -> None:
        if self._form_mode == "login":
            self._form_mode = "register"
            self._login_btn.setText("Зарегистрироваться")
            self._toggle_form_btn.setText("Уже есть аккаунт? Войти")
        else:
            self._form_mode = "login"
            self._login_btn.setText("Войти")
            self._toggle_form_btn.setText("Нет аккаунта? Зарегистрироваться")
        self._login_input.clear()
        self._password_input.clear()
        self._login_error.hide()
        self._login_input.setFocus()

    def _on_submit_click(self) -> None:
        username = self._login_input.text().strip()
        password = self._password_input.text().strip()

        if not username or not password:
            self._login_error.setText("Заполните логин и пароль")
            self._login_error.show()
            return

        self._login_btn.setEnabled(False)
        self._login_error.hide()

        try:
            if self._form_mode == "register":
                result = self._login_service.register(username, password)
            else:
                result = self._login_service.login(username, password)
            self._settings.auth_token = result.token
            self._settings.current_username = username
            self._settings.user_role = result.role
            self._current_username = username
            self._login_input.clear()
            self._password_input.clear()
            self._form_mode = "login"
            self._login_btn.setText("Войти")
            self._toggle_form_btn.setText("Нет аккаунта? Зарегистрироваться")
            self._update_auth_state(True)
        except Exception as exc:
            action = "регистрации" if self._form_mode == "register" else "входа"
            self._login_error.setText(f"Ошибка {action}: {exc}")
            self._login_error.show()
        finally:
            self._login_btn.setEnabled(True)

    # ---- Dashboard (logged in overview) --------------------------------------

    def _build_dashboard(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet(f"background-color: {BG_MAIN};")

        outer = QVBoxLayout(page)
        outer.setContentsMargins(20, 20, 20, 20)

        # Top-right action row: [power] [logout from account]
        logout_row = QHBoxLayout()
        logout_row.addStretch()

        _btn_style = f"""
            QPushButton {{
                background-color: {BG_SIDEBAR};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER_COLOR};
                border-radius: {CORNER_RADIUS}px;
                padding: 0 20px;
            }}
            QPushButton:hover {{
                background-color: {BG_SIDEBAR_HOVER};
            }}
        """

        quit_btn = QPushButton("⏻")
        quit_btn.setFixedHeight(44)
        quit_btn.setFont(QFont(FONT_FAMILY, 16))
        quit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        quit_btn.setToolTip("Закрыть приложение")
        quit_btn.clicked.connect(QApplication.quit)
        quit_btn.setStyleSheet(_btn_style)

        logout_btn = QPushButton("Выйти из аккаунта")
        logout_btn.setFixedHeight(44)
        logout_btn.setFont(QFont(FONT_FAMILY, 15))
        logout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        logout_btn.setToolTip("Выйти из аккаунта")
        logout_btn.clicked.connect(self._on_logout)
        logout_btn.setStyleSheet(_btn_style)

        logout_row.addWidget(quit_btn)
        logout_row.addSpacing(8)
        logout_row.addWidget(logout_btn)
        outer.addLayout(logout_row)

        # Center everything vertically
        outer.addStretch()

        # Title centered above tiles
        title = QLabel("EyeTracker")
        title.setFont(QFont(FONT_FAMILY, 36, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(title)
        outer.addSpacing(50)

        # Tiles container — 60% of content width
        _TILE_SIZE = 200
        _GAP = 16
        # 3 tiles wide: big square + gap + 2 action tiles stacked
        tiles_container = QWidget()
        tiles_container.setMaximumWidth(750)
        tiles_container.setStyleSheet("background: transparent;")
        tiles_row = QHBoxLayout(tiles_container)
        tiles_row.setContentsMargins(0, 0, 0, 0)
        tiles_row.setSpacing(_GAP)

        # Big tile — last opened test (square, same height as 2 small + gap)
        self._last_test_tile = self._build_last_test_tile(_TILE_SIZE * 2 + _GAP)
        tiles_row.addWidget(self._last_test_tile)

        # Right column — two square small tiles
        right_col = QVBoxLayout()
        right_col.setSpacing(_GAP)

        create_tile = self._build_action_tile("Создать тест", "+", self._on_tile_create, _TILE_SIZE)
        library_tile = self._build_action_tile("Библиотека", "☰", self._on_tile_library, _TILE_SIZE)
        right_col.addWidget(create_tile)
        right_col.addWidget(library_tile)

        tiles_row.addLayout(right_col)

        outer.addWidget(tiles_container, alignment=Qt.AlignmentFlag.AlignHCenter)

        outer.addStretch()

        return page

    def _build_action_tile(self, label: str, icon: str, on_click: Callable, size: int = 200) -> QPushButton:
        btn = QPushButton(f"{icon}\n{label}")
        btn.setFixedSize(size, size)
        btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        btn.setFont(QFont(FONT_FAMILY, 16, QFont.Weight.Bold))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(on_click)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {CARD_BG};
                color: {TEXT_PRIMARY};
                border: none;
                border-radius: {CORNER_RADIUS}px;
                padding: 20px;
            }}
            QPushButton:hover {{
                background-color: {CARD_HOVER};
            }}
        """)
        return btn

    def _build_last_test_tile(self, size: int = 416) -> QWidget:
        self._last_test_tile_size = size
        tile = QWidget()
        tile.setFixedSize(size, size)
        tile.setStyleSheet(f"""
            QWidget#lastTestTile {{
                background-color: {CARD_BG};
                border-radius: {CORNER_RADIUS}px;
            }}
            QWidget#lastTestTile:hover {{
                background-color: {CARD_HOVER};
            }}
        """)
        tile.setObjectName("lastTestTile")
        tile.setCursor(Qt.CursorShape.PointingHandCursor)
        tile.mousePressEvent = lambda e: self._on_tile_last_test()

        vbox = QVBoxLayout(tile)
        vbox.setContentsMargins(0, 0, 0, 16)
        vbox.setSpacing(8)

        self._last_test_cover = QLabel()
        self._last_test_cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._last_test_cover.setMinimumHeight(180)
        self._last_test_cover.setStyleSheet(f"""
            background-color: {BG_SIDEBAR};
            border-top-left-radius: {CORNER_RADIUS}px;
            border-top-right-radius: {CORNER_RADIUS}px;
        """)
        vbox.addWidget(self._last_test_cover, stretch=1)

        self._last_test_name = QLabel("Нет последнего теста")
        self._last_test_name.setFont(QFont(FONT_FAMILY, 15, QFont.Weight.Bold))
        self._last_test_name.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent; padding-left: 16px;")
        vbox.addWidget(self._last_test_name)

        return tile

    @staticmethod
    def _round_top_pixmap(pixmap: QPixmap, radius: int) -> QPixmap:
        """Return a copy of *pixmap* with top corners rounded."""
        rounded = QPixmap(pixmap.size())
        rounded.fill(Qt.GlobalColor.transparent)
        painter = QPainter(rounded)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        w, h = float(pixmap.width()), float(pixmap.height())
        path.moveTo(radius, 0)
        path.lineTo(w - radius, 0)
        path.arcTo(w - 2 * radius, 0, 2 * radius, 2 * radius, 90, -90)
        path.lineTo(w, h)
        path.lineTo(0, h)
        path.lineTo(0, radius)
        path.arcTo(0, 0, 2 * radius, 2 * radius, 180, -90)
        path.closeSubpath()
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, pixmap)
        painter.end()
        return rounded

    def _refresh_dashboard(self) -> None:
        test_id = self._settings.last_opened_test_id
        test = self._test_dao.load(test_id) if test_id else None

        placeholder_style = f"""
            background-color: {BG_SIDEBAR};
            color: {TEXT_SECONDARY};
            border-top-left-radius: {CORNER_RADIUS}px;
            border-top-right-radius: {CORNER_RADIUS}px;
        """

        if test is not None:
            cover_path = self._test_dao.get_cover_path(test)
            if cover_path.is_file():
                tile_w = self._last_test_tile_size
                cover_h = tile_w - 50  # leave room for name label
                pixmap = QPixmap(str(cover_path))
                scaled = pixmap.scaled(
                    tile_w,
                    cover_h,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
                # Crop to exact tile width × cover height
                if scaled.width() > tile_w or scaled.height() > cover_h:
                    x = (scaled.width() - tile_w) // 2
                    y = (scaled.height() - cover_h) // 2
                    scaled = scaled.copy(x, y, tile_w, cover_h)
                rounded = self._round_top_pixmap(scaled, CORNER_RADIUS)
                self._last_test_cover.setPixmap(rounded)
                self._last_test_cover.setStyleSheet("background: transparent;")
            else:
                self._last_test_cover.clear()
                self._last_test_cover.setText("Нет превью")
                self._last_test_cover.setStyleSheet(placeholder_style)
            self._last_test_name.setText(test.name)
        else:
            self._last_test_cover.clear()
            self._last_test_cover.setText("Нет превью")
            self._last_test_cover.setFont(QFont(FONT_FAMILY, 14))
            self._last_test_cover.setStyleSheet(placeholder_style)
            self._last_test_name.setText("Нет последнего теста")

    def _on_tile_create(self) -> None:
        self._select_sidebar_item("create_test")

    def _on_tile_library(self) -> None:
        self._select_sidebar_item("tests")

    def _on_tile_last_test(self) -> None:
        test_id = self._settings.last_opened_test_id
        if test_id and self._test_dao.load(test_id):
            self._select_sidebar_item("tests")
            self._show_test_detail(test_id)
        else:
            self._select_sidebar_item("tests")

    def logout(self) -> None:
        """Force logout — clears stored token and returns to login view."""
        self._settings.auth_token = None
        self._settings.current_username = ""
        self._settings.user_role = None
        self._update_auth_state(False)

    def _on_logout(self) -> None:
        self.logout()

    # ---- Other content pages -------------------------------------------------

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

    def _is_super_admin(self) -> bool:
        role = self._settings.user_role
        if role is not None:
            return role == "SUPER_ADMIN"
        return self._current_username.lower() == "admin"

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

        _checkbox_style = f"""
            QCheckBox {{
                color: {TEXT_PRIMARY};
                background: transparent;
                spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border: 1px solid {BORDER_COLOR};
                border-radius: 4px;
                background-color: {BG_SIDEBAR};
            }}
            QCheckBox::indicator:checked {{
                background-color: {BUTTON_BG};
                border-color: {BUTTON_BG};
            }}
        """

        self._skip_calibration_cb = QCheckBox("Пропустить калибровку")
        self._skip_calibration_cb.setFont(QFont(FONT_FAMILY, 14))
        self._skip_calibration_cb.setStyleSheet(_checkbox_style)
        self._skip_calibration_cb.setChecked(self._settings.skip_calibration)
        self._skip_calibration_cb.toggled.connect(self._on_skip_calibration_changed)

        skip_desc = QLabel("Запускать трекер без калибровки (с весами по умолчанию)")
        skip_desc.setFont(QFont(FONT_FAMILY, 12))
        skip_desc.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent; padding-left: 26px;")

        self._show_gaze_marker_cb = QCheckBox("Показывать маркер взгляда во время теста")
        self._show_gaze_marker_cb.setFont(QFont(FONT_FAMILY, 14))
        self._show_gaze_marker_cb.setStyleSheet(_checkbox_style)
        self._show_gaze_marker_cb.setChecked(self._settings.show_gaze_marker)
        self._show_gaze_marker_cb.toggled.connect(self._on_show_gaze_marker_changed)

        marker_desc = QLabel("Отображать точку взгляда поверх изображения (как в режиме демонстрации)")
        marker_desc.setFont(QFont(FONT_FAMILY, 12))
        marker_desc.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent; padding-left: 26px;")

        vbox.addWidget(title)
        vbox.addSpacing(30)
        vbox.addWidget(section_label)
        vbox.addSpacing(8)
        vbox.addWidget(self._monitor_combo)
        vbox.addSpacing(24)
        vbox.addWidget(self._skip_calibration_cb)
        vbox.addWidget(skip_desc)
        vbox.addSpacing(16)
        vbox.addWidget(self._show_gaze_marker_cb)
        vbox.addWidget(marker_desc)

        _spin_style = f"""
            QSpinBox {{
                background-color: {BG_SIDEBAR};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER_COLOR};
                border-radius: {CORNER_RADIUS}px;
                padding: 8px 12px;
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                width: 0;
            }}
        """

        duration_label = QLabel("Время показа изображения")
        duration_label.setFont(QFont(FONT_FAMILY, 14))
        duration_label.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")

        self._duration_spin = QSpinBox()
        self._duration_spin.setRange(1, 60)
        self._duration_spin.setSuffix(" сек")
        self._duration_spin.setValue(self._settings.image_display_duration_ms // 1000)
        self._duration_spin.setFixedWidth(160)
        self._duration_spin.setFont(QFont(FONT_FAMILY, 14))
        self._duration_spin.setStyleSheet(_spin_style)
        self._duration_spin.valueChanged.connect(self._on_duration_changed)

        duration_desc = QLabel("Продолжительность просмотра каждого изображения во время теста")
        duration_desc.setFont(QFont(FONT_FAMILY, 12))
        duration_desc.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")

        rate_label = QLabel("Частота трекинга взгляда")
        rate_label.setFont(QFont(FONT_FAMILY, 14))
        rate_label.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")

        self._timestep_spin = QSpinBox()
        self._timestep_spin.setRange(20, 200)
        self._timestep_spin.setSuffix(" мс")
        self._timestep_spin.setValue(self._settings.tracking_timestep_ms)
        self._timestep_spin.setFixedWidth(160)
        self._timestep_spin.setFont(QFont(FONT_FAMILY, 14))
        self._timestep_spin.setStyleSheet(_spin_style)
        self._timestep_spin.valueChanged.connect(self._on_timestep_changed)

        rate_desc = QLabel("Интервал между измерениями взгляда (меньше = выше частота)")
        rate_desc.setFont(QFont(FONT_FAMILY, 12))
        rate_desc.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")

        vbox.addSpacing(16)
        vbox.addWidget(duration_label)
        vbox.addSpacing(8)
        vbox.addWidget(self._duration_spin)
        vbox.addWidget(duration_desc)
        self._fixation_enabled_cb = QCheckBox("Детекция фиксаций")
        self._fixation_enabled_cb.setFont(QFont(FONT_FAMILY, 14))
        self._fixation_enabled_cb.setStyleSheet(_checkbox_style)
        self._fixation_enabled_cb.setChecked(self._settings.fixation_enabled)
        self._fixation_enabled_cb.toggled.connect(self._on_fixation_enabled_changed)

        fixation_enabled_desc = QLabel("Определять фиксации взгляда во время прохождения теста")
        fixation_enabled_desc.setFont(QFont(FONT_FAMILY, 12))
        fixation_enabled_desc.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent; padding-left: 26px;")

        k_label = QLabel("Порог радиуса фиксации (K)")
        k_label.setFont(QFont(FONT_FAMILY, 14))
        k_label.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")

        self._fixation_k_spin = QDoubleSpinBox()
        self._fixation_k_spin.setRange(10.0, 500.0)
        self._fixation_k_spin.setSingleStep(5.0)
        self._fixation_k_spin.setDecimals(1)
        self._fixation_k_spin.setSuffix(" px")
        self._fixation_k_spin.setValue(self._settings.fixation_radius_threshold_k)
        self._fixation_k_spin.setFixedWidth(160)
        self._fixation_k_spin.setFont(QFont(FONT_FAMILY, 14))
        self._fixation_k_spin.setStyleSheet(_spin_style.replace("QSpinBox", "QDoubleSpinBox"))
        self._fixation_k_spin.valueChanged.connect(self._on_fixation_k_changed)

        k_desc = QLabel("Максимальный радиус в пикселях, при котором взгляд считается фиксацией")
        k_desc.setFont(QFont(FONT_FAMILY, 12))
        k_desc.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")

        window_label = QLabel("Окно детекции фиксации")
        window_label.setFont(QFont(FONT_FAMILY, 14))
        window_label.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")

        self._fixation_window_spin = QSpinBox()
        self._fixation_window_spin.setRange(3, 50)
        self._fixation_window_spin.setSuffix(" точек")
        self._fixation_window_spin.setValue(self._settings.fixation_window_size_samples)
        self._fixation_window_spin.setFixedWidth(160)
        self._fixation_window_spin.setFont(QFont(FONT_FAMILY, 14))
        self._fixation_window_spin.setStyleSheet(_spin_style)
        self._fixation_window_spin.valueChanged.connect(self._on_fixation_window_changed)

        window_desc = QLabel("Длина скользящего временного окна для определения фиксации")
        window_desc.setFont(QFont(FONT_FAMILY, 12))
        window_desc.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")

        admin_section = QWidget()
        admin_section.setStyleSheet("background: transparent;")
        admin_vbox = QVBoxLayout(admin_section)
        admin_vbox.setContentsMargins(0, 0, 0, 0)
        admin_vbox.setSpacing(0)

        admin_vbox.addSpacing(16)
        admin_vbox.addWidget(rate_label)
        admin_vbox.addSpacing(8)
        admin_vbox.addWidget(self._timestep_spin)
        admin_vbox.addWidget(rate_desc)
        admin_vbox.addSpacing(16)
        admin_vbox.addWidget(self._fixation_enabled_cb)
        admin_vbox.addWidget(fixation_enabled_desc)
        admin_vbox.addSpacing(16)
        admin_vbox.addWidget(k_label)
        admin_vbox.addSpacing(8)
        admin_vbox.addWidget(self._fixation_k_spin)
        admin_vbox.addWidget(k_desc)
        admin_vbox.addSpacing(16)
        admin_vbox.addWidget(window_label)
        admin_vbox.addSpacing(8)
        admin_vbox.addWidget(self._fixation_window_spin)
        admin_vbox.addWidget(window_desc)

        server_url_label = QLabel("URL сервера")
        server_url_label.setFont(QFont(FONT_FAMILY, 14))
        server_url_label.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")

        self._server_url_edit = QLineEdit()
        self._server_url_edit.setFixedWidth(400)
        self._server_url_edit.setFont(QFont(FONT_FAMILY, 14))
        self._server_url_edit.setPlaceholderText("http://localhost:8080")
        self._server_url_edit.setText(self._settings.server_url or "")
        self._server_url_edit.setStyleSheet(f"""
            QLineEdit {{
                background-color: {BG_SIDEBAR};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER_COLOR};
                border-radius: {CORNER_RADIUS}px;
                padding: 8px 12px;
            }}
        """)
        self._server_url_edit.editingFinished.connect(self._on_server_url_changed)

        server_url_desc = QLabel("Адрес бэкенда. Оставьте пустым для локального режима.")
        server_url_desc.setFont(QFont(FONT_FAMILY, 12))
        server_url_desc.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")

        admin_vbox.addSpacing(16)
        admin_vbox.addWidget(server_url_label)
        admin_vbox.addSpacing(8)
        admin_vbox.addWidget(self._server_url_edit)
        admin_vbox.addWidget(server_url_desc)

        self._admin_section = admin_section
        admin_section.setVisible(self._is_super_admin())
        vbox.addWidget(admin_section)
        vbox.addStretch()

        return page

    def _refresh_monitor_combo(self):
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

    def _on_skip_calibration_changed(self, checked: bool) -> None:
        self._settings.skip_calibration = checked

    def _on_show_gaze_marker_changed(self, checked: bool) -> None:
        self._settings.show_gaze_marker = checked

    def _on_duration_changed(self, seconds: int) -> None:
        self._settings.image_display_duration_ms = seconds * 1000

    def _on_timestep_changed(self, ms: int) -> None:
        self._settings.tracking_timestep_ms = ms

    def _on_fixation_enabled_changed(self, checked: bool) -> None:
        self._settings.fixation_enabled = checked

    def _on_fixation_k_changed(self, value: float) -> None:
        self._settings.fixation_radius_threshold_k = value

    def _on_fixation_window_changed(self, samples: int) -> None:
        self._settings.fixation_window_size_samples = samples

    def _on_server_url_changed(self) -> None:
        url = self._server_url_edit.text().strip()
        self._settings.server_url = url if url else None

    # ---- Help page ------------------------------------------------------------

    _FAQ_ITEMS = [
        (
            "Как создать тест?",
            "Перейдите в раздел «Создать тест» в боковом меню. "
            "Выберите «Заполнить форму», укажите название теста, "
            "загрузите обложку и добавьте изображения. Нажмите «Создать».",
        ),
        (
            "Как редактировать тест?",
            "Откройте тест из библиотеки. На странице теста нажмите «Редактировать». "
            "Измените название, обложку или изображения. Нажмите «Сохранить».",
        ),
        (
            "Как изменить порядок изображений в тесте?",
            "В режиме редактирования теста перетащите изображение мышкой "
            "на нужную позицию. Порядок сохранится автоматически при сохранении теста.",
        ),
        (
            "Как работает отслеживание взгляда?",
            "После калибровки система использует веб-камеру для отслеживания "
            "положения глаз. На основе калибровочных данных она предсказывает, "
            "куда вы смотрите на экране. Красная точка показывает текущую позицию взгляда.",
        ),
        (
            "Как сменить монитор для трекинга?",
            "Перейдите в «Настройки» и выберите нужный монитор из выпадающего списка. "
            "По умолчанию используется основной монитор.",
        ),
        (
            "Что такое зоны интереса (ROI)?",
            "Зоны интереса — это области на изображении, для которых автоматически "
            "определяется, попал ли взгляд участника в эту зону во время теста. "
            "Чтобы добавить зону: откройте тест, нажмите на изображение, выберите «Добавить зону», "
            "нарисуйте выпуклый многоугольник кликами по точкам, закройте его двойным кликом на "
            "первой точке, задайте название и цвет, нажмите «Сохранить». "
            "Зон интереса на одном изображении может быть несколько. "
            "В результатах теста для каждого прохождения отображается, была ли зона достигнута (✓).",
        ),
        (
            "Как работает режим «Только первая фиксация»?",
            "При создании зоны интереса можно включить флажок «Только первая фиксация». "
            "В этом режиме зона считается достигнутой только если первая фиксация взгляда "
            "на изображении попала именно в неё. Последующие фиксации не учитываются. "
            "Это полезно для изучения того, на что участник обратил внимание в первую очередь.",
        ),
    ]

    def _build_help_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet(f"background-color: {BG_MAIN};")

        outer = QVBoxLayout(page)
        outer.setContentsMargins(40, 40, 40, 40)
        outer.setSpacing(0)

        title = QLabel("Помощь")
        title.setFont(QFont(FONT_FAMILY, 36, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")
        outer.addWidget(title)
        outer.addSpacing(24)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"background-color: {BG_MAIN}; border: none;")

        content = QWidget()
        content.setStyleSheet(f"background-color: {BG_MAIN};")
        vbox = QVBoxLayout(content)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(8)

        for question, answer in self._FAQ_ITEMS:
            vbox.addWidget(self._build_faq_item(question, answer))

        vbox.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll)

        return page

    def _build_faq_item(self, question: str, answer: str) -> QWidget:
        container = QWidget()
        container.setStyleSheet(f"""
            QWidget#faqItem {{
                background-color: {CARD_BG};
                border-radius: {CORNER_RADIUS}px;
            }}
        """)
        container.setObjectName("faqItem")

        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(16, 12, 16, 12)
        vbox.setSpacing(0)

        btn = QPushButton(f"▸  {question}")
        btn.setFont(QFont(FONT_FAMILY, 14, QFont.Weight.Bold))
        btn.setFlat(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                color: {TEXT_PRIMARY};
                text-align: left;
                border: none;
                background: transparent;
                padding: 4px 0;
            }}
            QPushButton:hover {{
                color: {BUTTON_BG};
            }}
        """)

        answer_label = QLabel(answer)
        answer_label.setFont(QFont(FONT_FAMILY, 13))
        answer_label.setWordWrap(True)
        answer_label.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent; padding: 8px 0 4px 20px;")
        answer_label.hide()

        def toggle():
            if answer_label.isVisible():
                answer_label.hide()
                btn.setText(f"▸  {question}")
            else:
                answer_label.show()
                btn.setText(f"▾  {question}")

        btn.clicked.connect(toggle)

        vbox.addWidget(btn)
        vbox.addWidget(answer_label)

        return container

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

    # ---- Tests library navigation ---------------------------------------------

    def _build_tests_page(self) -> QWidget:
        page = TestLibraryPage(dao=self._test_dao)
        page.test_selected.connect(self._show_test_detail)
        page.create_requested.connect(lambda: self._select_sidebar_item("create_test"))
        return page

    def _show_test_detail(self, test_id: str, mode: FormMode = FormMode.VIEW) -> None:
        self._remove_detail_page()
        test = self._test_dao.load(test_id)
        if test is None:
            return
        self._settings.last_opened_test_id = test_id
        self._detail_page = TestFormPage(dao=self._test_dao, mode=mode, test_data=test)
        if mode == FormMode.EDIT:
            self._detail_page.set_draft_cache(self._draft_cache, "edit", test_id)
            self._detail_page.back_requested.connect(lambda tid=test_id: self._show_test_detail(tid, FormMode.VIEW))
        else:
            self._detail_page.back_requested.connect(self._back_to_tests)
        self._detail_page.edit_requested.connect(lambda tid=test_id: self._show_test_detail(tid, FormMode.EDIT))
        self._detail_page.run_test_requested.connect(lambda tid=test_id: self._on_run_test(tid))
        self._detail_page.results_requested.connect(lambda tid=test_id: self._show_records_list(tid))
        self._detail_page.test_updated.connect(lambda tid=test_id: self._show_test_detail(tid, FormMode.VIEW))
        self._detail_page.test_deleted.connect(self._back_to_tests)
        self._content_stack.addWidget(self._detail_page)
        self._content_stack.setCurrentWidget(self._detail_page)

        if mode == FormMode.EDIT and self._draft_cache.exists():
            draft = self._draft_cache.load()
            if draft and draft.draft_type == "edit" and draft.test_id == test_id:
                self._detail_page.restore_from_draft(draft)
                QMessageBox.information(self, "Восстановление", "Черновик был восстановлен.")

    def _on_run_test(self, test_id: str) -> None:
        test = self._test_dao.load(test_id)
        if test is None:
            return
        self._remove_detail_page()
        self._show_readiness_page(test)

    def _show_readiness_page(self, test: TestData) -> None:
        self._remove_readiness_page()
        self._readiness_test_id = test.id

        page = QWidget()
        page.setStyleSheet(f"background-color: {BG_MAIN};")

        vbox = QVBoxLayout(page)
        vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("Готовы начать?")
        title.setFont(QFont(FONT_FAMILY, 36, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel(test.name)
        subtitle.setFont(QFont(FONT_FAMILY, 18))
        subtitle.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        desc = QLabel(
            "После нажатия «Начать» будет запущена калибровка,\n"
            "затем последовательный показ изображений теста."
        )
        desc.setFont(QFont(FONT_FAMILY, 14))
        desc.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)

        start_btn = QPushButton("Начать")
        start_btn.setFixedSize(200, 44)
        start_btn.setFont(QFont(FONT_FAMILY, 15, QFont.Weight.Bold))
        start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        start_btn.setStyleSheet(f"""
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
        start_btn.clicked.connect(lambda: self._on_readiness_start(test))

        back_btn = QPushButton("Назад")
        back_btn.setFixedSize(200, 44)
        back_btn.setFont(QFont(FONT_FAMILY, 15))
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {BUTTON_BG};
                border: 1px solid {BUTTON_BG};
                border-radius: {CORNER_RADIUS}px;
            }}
            QPushButton:hover {{
                background-color: {BUTTON_BG};
                color: white;
            }}
        """)
        back_btn.clicked.connect(lambda: self._on_readiness_back(test.id))

        vbox.addWidget(title)
        vbox.addSpacing(10)
        vbox.addWidget(subtitle)
        vbox.addSpacing(20)
        vbox.addWidget(desc)
        vbox.addSpacing(30)
        vbox.addWidget(start_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        vbox.addSpacing(10)
        vbox.addWidget(back_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self._readiness_page = page
        self._content_stack.addWidget(page)
        self._content_stack.setCurrentWidget(page)

    def _on_readiness_start(self, test: TestData) -> None:
        self._remove_readiness_page()
        self._select_sidebar_item("overview")
        self._on_start_test_run(test)

    def _on_readiness_back(self, test_id: str) -> None:
        self._show_test_detail(test_id)
        self._remove_readiness_page()

    def _remove_readiness_page(self) -> None:
        if self._readiness_page is not None:
            self._content_stack.removeWidget(self._readiness_page)
            self._readiness_page.deleteLater()
            self._readiness_page = None
        self._readiness_test_id = None

    def _back_to_tests(self) -> None:
        self._remove_detail_page()
        page = self._content_pages.get("tests")
        if isinstance(page, TestLibraryPage):
            page.refresh()
        if page:
            self._content_stack.setCurrentWidget(page)

    def _remove_detail_page(self) -> None:
        if self._detail_page is not None:
            self._content_stack.removeWidget(self._detail_page)
            self._detail_page.deleteLater()
            self._detail_page = None

    # ---- Records navigation --------------------------------------------------

    def _show_records_list(self, test_id: str) -> None:
        test = self._test_dao.load(test_id)
        if test is None:
            return
        self._remove_detail_page()
        self._remove_record_detail_page()
        self._remove_records_page()

        self._records_page = RecordsListPage(
            record_service=self._record_service,
            test_id=test_id,
            test_name=test.name,
            on_view_report=lambda rid, tn=test.name, tid=test_id: self._show_record_detail(rid, tn, tid),
            on_back=lambda tid=test_id: self._back_from_records_list(tid),
            test_dao=self._test_dao,
            test=test,
        )
        self._content_stack.addWidget(self._records_page)
        self._content_stack.setCurrentWidget(self._records_page)

    def _back_from_records_list(self, test_id: str) -> None:
        # Show test detail first so the stack never flashes a wrong page
        self._show_test_detail(test_id)
        self._remove_records_page()

    def _show_record_detail(self, record_id: str, test_name: str, test_id: str) -> None:
        self._remove_record_detail_page()

        self._record_detail_page = RecordDetailPage(
            record_service=self._record_service,
            record_id=record_id,
            test_name=test_name,
            on_back=lambda tid=test_id: self._back_from_record_detail(tid),
            test_dao=self._test_dao,
        )
        self._content_stack.addWidget(self._record_detail_page)
        self._content_stack.setCurrentWidget(self._record_detail_page)

    def _back_from_record_detail(self, test_id: str) -> None:
        self._remove_record_detail_page()
        self._show_records_list(test_id)

    def _remove_records_page(self) -> None:
        if self._records_page is not None:
            self._content_stack.removeWidget(self._records_page)
            self._records_page.deleteLater()
            self._records_page = None

    def _remove_record_detail_page(self) -> None:
        if self._record_detail_page is not None:
            self._content_stack.removeWidget(self._record_detail_page)
            self._record_detail_page.deleteLater()
            self._record_detail_page = None

    # ---- Create test navigation ---------------------------------------------

    def _build_create_test_page(self) -> QWidget:
        page = CreateTestChoicePage()
        page.form_chosen.connect(self._show_create_test_form)
        page.import_chosen.connect(self._on_import_test_chosen)
        return page

    def _show_create_test_form(self) -> None:
        self._remove_detail_page()
        self._detail_page = TestFormPage(dao=self._test_dao, mode=FormMode.CREATE)
        self._detail_page.set_draft_cache(self._draft_cache, "create")
        self._detail_page.back_requested.connect(self._show_create_test_choice)
        self._detail_page.test_created.connect(self._on_test_created)
        self._content_stack.addWidget(self._detail_page)
        self._content_stack.setCurrentWidget(self._detail_page)

        if self._draft_cache.exists():
            draft = self._draft_cache.load()
            if draft and draft.draft_type == "create":
                self._detail_page.restore_from_draft(draft)
                QMessageBox.information(self, "Восстановление", "Черновик был восстановлен.")

    def _show_create_test_choice(self) -> None:
        self._remove_detail_page()
        page = self._content_pages.get("create_test")
        if page:
            self._content_stack.setCurrentWidget(page)

    def _on_test_created(self) -> None:
        self._show_create_test_choice()

    def _on_import_test_chosen(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Импортировать тест", "", "ZIP архив (*.zip)"
        )
        if not path:
            return
        try:
            from eyetracker.data.test.import_zip import import_test_zip
            test = import_test_zip(Path(path), self._test_dao)
        except Exception as exc:
            QMessageBox.warning(self, "Ошибка", f"Не удалось импортировать тест:\n{exc}")
            return

        self._select_sidebar_item("tests")
        self._show_test_detail(test.id, FormMode.EDIT)
        if self._detail_page is not None:
            self._detail_page._auto_save_draft()

    # ---- Keys ----------------------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent):  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            if self._record_detail_page is not None and self._content_stack.currentWidget() is self._record_detail_page:
                self._record_detail_page._on_back()
            elif self._records_page is not None and self._content_stack.currentWidget() is self._records_page:
                self._records_page._on_back()
            elif self._readiness_page is not None and self._content_stack.currentWidget() is self._readiness_page:
                if self._readiness_test_id is not None:
                    self._on_readiness_back(self._readiness_test_id)
            elif self._detail_page is not None and self._content_stack.currentWidget() is self._detail_page:
                self._detail_page.back_requested.emit()
            elif self._current_tab_id != "overview":
                self._select_sidebar_item("overview")
            else:
                reply = QMessageBox.question(
                    self,
                    "Выход",
                    "Вы уверены, что хотите выйти?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if reply == QMessageBox.StandardButton.Yes:
                    QApplication.quit()
        else:
            super().keyPressEvent(event)
