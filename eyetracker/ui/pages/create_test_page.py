"""Choice page: create test via Form or TEST.json."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from eyetracker.ui.theme import (
    BG_MAIN,
    CARD_BG,
    CARD_HOVER,
    CORNER_RADIUS,
    FONT_FAMILY,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


class CreateTestChoicePage(QWidget):
    """Two-card page: 'Form' or 'TEST.json'."""

    form_chosen = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {BG_MAIN};")

        root = QVBoxLayout(self)
        root.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("Создать тест")
        title.setFont(QFont(FONT_FAMILY, 36, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel("Выберите способ создания")
        subtitle.setFont(QFont(FONT_FAMILY, 16))
        subtitle.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        root.addWidget(title)
        root.addSpacing(6)
        root.addWidget(subtitle)
        root.addSpacing(30)

        cards_row = QHBoxLayout()
        cards_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cards_row.setSpacing(20)
        cards_row.addWidget(self._make_card(
            icon="📝",
            heading="Форма",
            description="Создание теста\nчерез форму в приложении",
            on_click=self._on_form,
        ))
        cards_row.addWidget(self._make_card(
            icon="📁",
            heading="TEST.json",
            description="Загрузка папки\nтеста с TEST.json",
            on_click=self._on_json,
        ))
        root.addLayout(cards_row)

    # -- helpers -------------------------------------------------------------

    def _make_card(self, icon: str, heading: str, description: str, on_click) -> QPushButton:
        btn = QPushButton()
        btn.setFixedSize(200, 180)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {CARD_BG};
                border: 1px solid {CARD_BG};
                border-radius: {CORNER_RADIUS}px;
            }}
            QPushButton:hover {{
                background-color: {CARD_HOVER};
                border-color: {CARD_HOVER};
            }}
        """)

        layout = QVBoxLayout(btn)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(8)

        icon_label = QLabel(icon)
        icon_label.setFont(QFont(FONT_FAMILY, 28))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet("background: transparent;")
        icon_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        title_label = QLabel(heading)
        title_label.setFont(QFont(FONT_FAMILY, 15, QFont.Weight.Bold))
        title_label.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        desc_label = QLabel(description)
        desc_label.setFont(QFont(FONT_FAMILY, 12))
        desc_label.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        layout.addWidget(icon_label)
        layout.addWidget(title_label)
        layout.addWidget(desc_label)

        btn.clicked.connect(on_click)
        return btn

    def _on_form(self) -> None:
        self.form_chosen.emit()

    def _on_json(self) -> None:
        QMessageBox.information(self, "TEST.json", "Импорт из TEST.json будет добавлен позже")
