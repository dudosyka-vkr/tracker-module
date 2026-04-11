"""Unified form page for creating, viewing, and editing a test."""

from __future__ import annotations

import logging
from enum import Enum, auto
from pathlib import Path

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QFont, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from eyetracker.data.test import TestDao, TestData
from eyetracker.ui.widgets.image_grid import ImageGridWidget
from eyetracker.ui.theme import (
    BG_MAIN,
    BG_SIDEBAR,
    BORDER_COLOR,
    BUTTON_BG,
    BUTTON_HOVER,
    CORNER_RADIUS,
    ERROR_COLOR,
    FONT_FAMILY,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

logger = logging.getLogger(__name__)

_IMAGE_FILTER = "Изображения (*.png *.jpg *.jpeg *.bmp *.gif *.webp)"


class FormMode(Enum):
    CREATE = auto()
    VIEW = auto()
    EDIT = auto()


def validate_form(
    name: str,
    cover_path: str | None,
    image_paths: list[str],
) -> dict[str, str]:
    """Return a dict of field-key → error message (empty if valid)."""
    errors: dict[str, str] = {}
    if not name.strip():
        errors["name"] = "Название не может быть пустым"
    if cover_path is None:
        errors["cover"] = "Выберите обложку"
    if len(image_paths) < 1:
        errors["images"] = "Добавьте хотя бы одно изображение"
    return errors


def pick_image(parent: QWidget) -> str | None:
    """Open a file-picker for images. Returns path or None."""
    path, _ = QFileDialog.getOpenFileName(parent, "Выберите изображение", "", _IMAGE_FILTER)
    if not path:
        return None
    if QPixmap(path).isNull():
        QMessageBox.warning(parent, "Ошибка", "Не удалось загрузить изображение")
        return None
    return path


class TestFormPage(QWidget):
    """Form for creating / viewing / editing a test."""

    back_requested = pyqtSignal()
    test_created = pyqtSignal(str)  # carries new test_id
    test_updated = pyqtSignal()
    test_deleted = pyqtSignal()
    edit_requested = pyqtSignal()
    run_test_requested = pyqtSignal()
    results_requested = pyqtSignal()

    def __init__(
        self,
        dao: TestDao,
        mode: FormMode = FormMode.CREATE,
        test_data: TestData | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._dao = dao
        self._mode = mode
        self._test_data = test_data
        self._cover_path: str | None = None
        self._original_name: str | None = None
        self._original_cover_path: str | None = None
        self._image_grid: ImageGridWidget | None = None
        self._images_error: QLabel | None = None
        self.setStyleSheet(f"background-color: {BG_MAIN};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # -- top bar ---------------------------------------------------------
        root.addWidget(self._build_top_bar())

        # -- scrollable body -------------------------------------------------
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(40, 30, 40, 30)
        body_layout.setSpacing(0)

        self._build_name_section(body_layout)
        body_layout.addSpacing(24)
        self._build_cover_section(body_layout)
        if mode != FormMode.CREATE:
            body_layout.addSpacing(16)
            self._build_images_section(body_layout)
        body_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        root.addWidget(scroll)

        # -- populate data for view/edit -------------------------------------
        if test_data is not None and mode in (FormMode.VIEW, FormMode.EDIT):
            self._populate(test_data)

    # -- top bar -------------------------------------------------------------

    def _build_top_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(52)
        bar.setStyleSheet(f"background-color: {BG_MAIN}; border-bottom: 1px solid {BORDER_COLOR};")

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 16, 0)

        back_btn = QPushButton("← Назад")
        back_btn.setFont(QFont(FONT_FAMILY, 13))
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.setStyleSheet(f"""
            QPushButton {{
                color: {BUTTON_BG};
                background: transparent;
                border: none;
                padding: 6px 12px;
            }}
            QPushButton:hover {{ color: {BUTTON_HOVER}; }}
        """)
        back_btn.clicked.connect(self.back_requested.emit)

        titles = {
            FormMode.CREATE: "Создание теста",
            FormMode.VIEW: "Просмотр теста",
            FormMode.EDIT: "Редактирование теста",
        }
        title = QLabel(titles[self._mode])
        title.setFont(QFont(FONT_FAMILY, 16, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(back_btn)
        layout.addStretch()
        layout.addWidget(title)
        layout.addStretch()

        if self._mode == FormMode.CREATE:
            layout.addWidget(self._make_action_button("Создать", self._on_create_clicked))
        elif self._mode == FormMode.EDIT:
            layout.addWidget(self._make_action_button("Сохранить", self._on_save_clicked))
        elif self._mode == FormMode.VIEW:
            self._build_view_actions(layout)

        return bar

    def _make_action_button(self, text: str, handler) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedSize(120, 34)
        btn.setFont(QFont(FONT_FAMILY, 13, QFont.Weight.Bold))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
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
        btn.clicked.connect(handler)
        return btn

    def _build_view_actions(self, layout: QHBoxLayout) -> None:
        actions = [
            ("Редактировать", self._on_edit_clicked),
            ("Скопировать код", self._on_copy_code_clicked),
            ("Пройти", self._on_use_clicked),
            ("Результаты", self._on_results_clicked),
            ("Выгрузить Json", self._on_export_clicked),
            ("Удалить", self._on_delete_clicked),
        ]
        for text, handler in actions:
            btn = QPushButton(text)
            btn.setFixedHeight(34)
            btn.setFont(QFont(FONT_FAMILY, 12))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if text == "Удалить":
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: transparent;
                        color: {ERROR_COLOR};
                        border: 1px solid {ERROR_COLOR};
                        border-radius: {CORNER_RADIUS}px;
                        padding: 0 14px;
                    }}
                    QPushButton:hover {{
                        background-color: {ERROR_COLOR};
                        color: white;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: transparent;
                        color: {BUTTON_BG};
                        border: 1px solid {BUTTON_BG};
                        border-radius: {CORNER_RADIUS}px;
                        padding: 0 14px;
                    }}
                    QPushButton:hover {{
                        background-color: {BUTTON_BG};
                        color: white;
                    }}
                """)
            btn.clicked.connect(handler)
            layout.addWidget(btn)

    # -- name section --------------------------------------------------------

    def _build_name_section(self, parent_layout: QVBoxLayout) -> None:
        label = QLabel("Название")
        label.setFont(QFont(FONT_FAMILY, 14, QFont.Weight.Bold))
        label.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Введите название теста")
        self._name_edit.setFont(QFont(FONT_FAMILY, 14))
        self._name_edit.setFixedHeight(40)
        self._name_edit.setStyleSheet(f"""
            QLineEdit {{
                background-color: {BG_SIDEBAR};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER_COLOR};
                border-radius: {CORNER_RADIUS}px;
                padding: 0 12px;
            }}
            QLineEdit:focus {{
                border-color: {BUTTON_BG};
            }}
        """)

        if self._mode == FormMode.VIEW:
            self._name_edit.setReadOnly(True)

        self._name_error = self._make_error_label()

        parent_layout.addWidget(label)
        parent_layout.addSpacing(6)
        parent_layout.addWidget(self._name_edit)
        parent_layout.addSpacing(4)
        parent_layout.addWidget(self._name_error)

    # -- cover section -------------------------------------------------------

    def _build_cover_section(self, parent_layout: QVBoxLayout) -> None:
        label = QLabel("Обложка")
        label.setFont(QFont(FONT_FAMILY, 14, QFont.Weight.Bold))
        label.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")

        self._cover_preview = QPushButton()
        self._cover_preview.setFixedSize(200, 200)
        self._cover_preview.setFont(QFont(FONT_FAMILY, 12))
        self._cover_preview.setText("Нет обложки\n\nНажмите для выбора")
        self._cover_preview.setStyleSheet(f"""
            QPushButton {{
                background-color: {BG_SIDEBAR};
                border: 2px dashed {BORDER_COLOR};
                border-radius: {CORNER_RADIUS}px;
                color: {TEXT_SECONDARY};
            }}
            QPushButton:hover {{
                border-color: {TEXT_SECONDARY};
            }}
        """)

        if self._mode == FormMode.VIEW:
            self._cover_preview.setEnabled(False)
        else:
            self._cover_preview.setCursor(Qt.CursorShape.PointingHandCursor)
            self._cover_preview.clicked.connect(self._on_choose_cover)

        self._cover_error = self._make_error_label()

        parent_layout.addWidget(label)
        parent_layout.addSpacing(6)
        parent_layout.addWidget(self._cover_preview, alignment=Qt.AlignmentFlag.AlignLeft)
        parent_layout.addSpacing(4)
        parent_layout.addWidget(self._cover_error)

    # -- images section ------------------------------------------------------

    def _build_images_section(self, parent_layout: QVBoxLayout) -> None:
        label = QLabel("Изображения теста")
        label.setFont(QFont(FONT_FAMILY, 14, QFont.Weight.Bold))
        label.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")

        readonly = self._mode == FormMode.VIEW
        self._image_grid = ImageGridWidget(readonly=readonly)
        self._image_grid.add_clicked.connect(self._on_add_image)
        if self._mode == FormMode.EDIT:
            self._image_grid.roi_saved.connect(self._on_roi_saved)

        self._images_error = self._make_error_label()

        parent_layout.addWidget(label)
        parent_layout.addSpacing(8)
        parent_layout.addWidget(self._image_grid)
        parent_layout.addSpacing(4)
        parent_layout.addWidget(self._images_error)

    # -- populate from existing test -----------------------------------------

    def _populate(self, test: TestData) -> None:
        self._name_edit.setText(test.name)
        self._original_name = test.name

        cover_path = str(self._dao.get_cover_path(test))
        self._set_cover_display(cover_path)
        self._original_cover_path = cover_path

        if self._test_data is not None:
            self._image_grid.set_regions(self._test_data.image_regions)
        image_paths = [str(self._dao.get_image_path(test, f)) for f in test.image_filenames]
        self._image_grid.set_images(image_paths)

    def _set_cover_display(self, path: str) -> None:
        self._cover_path = path
        pm = QPixmap(path).scaled(
            200, 200,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._cover_preview.setText("")
        self._cover_preview.setIcon(QIcon(pm))
        self._cover_preview.setIconSize(QSize(196, 196))
        self._cover_preview.setStyleSheet(f"""
            QPushButton {{
                background-color: {BG_SIDEBAR};
                border: 1px solid {BORDER_COLOR};
                border-radius: {CORNER_RADIUS}px;
            }}
            QPushButton:hover {{
                border-color: {TEXT_SECONDARY};
            }}
        """)

    # -- actions -------------------------------------------------------------

    def _on_choose_cover(self) -> None:
        path = pick_image(self)
        if path is None:
            return
        self._set_cover_display(path)
        self._cover_error.setVisible(False)

    def _on_add_image(self) -> None:
        if self._image_grid is None:
            return
        path = pick_image(self)
        if path is None:
            return

        if self._mode == FormMode.EDIT and self._test_data is not None:
            try:
                self._test_data = self._dao.add_image(self._test_data.id, Path(path))
            except Exception as exc:
                logger.error("Failed to upload image: %s", exc)
                QMessageBox.warning(self, "Ошибка", f"Не удалось загрузить изображение: {exc}")
                return
            new_filename = self._test_data.image_filenames[-1]
            path = str(self._dao.get_image_path(self._test_data, new_filename))

        if not self._image_grid.add_image(path):
            QMessageBox.warning(self, "Ошибка", "Не удалось загрузить изображение")
            return
        if self._images_error is not None:
            self._images_error.setVisible(False)

    def _on_create_clicked(self) -> None:
        errors: dict[str, str] = {}
        if not self._name_edit.text().strip():
            errors["name"] = "Название не может быть пустым"
        if self._cover_path is None:
            errors["cover"] = "Выберите обложку"
        self._show_errors(errors)
        if errors:
            return

        try:
            test = self._dao.create(
                name=self._name_edit.text().strip(),
                cover_src=Path(self._cover_path),  # type: ignore[arg-type]
                image_srcs=[],
            )
            self.test_created.emit(test.id)
        except OSError as exc:
            logger.error("Failed to create test: %s", exc)
            QMessageBox.warning(self, "Ошибка", f"Не удалось сохранить тест: {exc}")

    def _on_save_clicked(self) -> None:
        errors: dict[str, str] = {}
        if not self._name_edit.text().strip():
            errors["name"] = "Название не может быть пустым"
        if self._cover_path is None:
            errors["cover"] = "Выберите обложку"
        self._show_errors(errors)
        if errors:
            return
        if self._test_data is None:
            return
        new_name = self._name_edit.text().strip()
        try:
            if new_name != self._original_name:
                self._test_data = self._dao.update_name(self._test_data.id, new_name)
                self._original_name = new_name
            if self._cover_path != self._original_cover_path:
                self._test_data = self._dao.update_cover(
                    self._test_data.id, Path(self._cover_path)  # type: ignore[arg-type]
                )
                self._original_cover_path = self._cover_path
        except Exception as exc:
            logger.error("Failed to update test: %s", exc)
            QMessageBox.warning(self, "Ошибка", f"Не удалось сохранить тест: {exc}")
            return
        self.test_updated.emit()

    def _on_edit_clicked(self) -> None:
        self.edit_requested.emit()

    def _on_copy_code_clicked(self) -> None:
        if self._test_data is None:
            return
        try:
            code = self._dao.get_token(self._test_data.id)
        except Exception as exc:
            QMessageBox.warning(self, "Ошибка", f"Не удалось получить код: {exc}")
            return
        QApplication.clipboard().setText(code)
        QMessageBox.information(self, "Код скопирован", f"Код теста {code} скопирован в буфер обмена")

    def _on_use_clicked(self) -> None:
        self.run_test_requested.emit()

    def _on_results_clicked(self) -> None:
        self.results_requested.emit()

    def _on_export_clicked(self) -> None:
        if self._test_data is None:
            return
        default_name = f"{self._test_data.name}.zip"
        path, _ = QFileDialog.getSaveFileName(
            self, "Экспорт теста", default_name, "ZIP архив (*.zip)"
        )
        if not path:
            return
        try:
            from eyetracker.data.test.export import export_test_zip
            export_test_zip(self._test_data, self._dao, Path(path))
            QMessageBox.information(self, "Готово", f"Тест экспортирован:\n{path}")
        except Exception as exc:
            logger.error("Export failed: %s", exc)
            QMessageBox.warning(self, "Ошибка", f"Не удалось экспортировать тест:\n{exc}")

    def _on_delete_clicked(self) -> None:
        if self._test_data is None:
            return
        reply = QMessageBox.question(
            self,
            "Удалить тест",
            f"Удалить тест «{self._test_data.name}»?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            self._dao.delete(self._test_data.id)
            self.test_deleted.emit()
        except OSError as exc:
            logger.error("Failed to delete test: %s", exc)
            QMessageBox.warning(self, "Ошибка", f"Не удалось удалить тест: {exc}")

    def _on_roi_saved(self, filename: str, rois: list) -> None:
        if self._test_data is None:
            return
        self._test_data.image_regions[filename] = rois
        self._dao.save_regions(self._test_data.id, self._test_data.image_regions)

    # -- validation display --------------------------------------------------

    def _show_errors(self, errors: dict[str, str]) -> None:
        self._name_error.setText(errors.get("name", ""))
        self._name_error.setVisible("name" in errors)

        self._cover_error.setText(errors.get("cover", ""))
        self._cover_error.setVisible("cover" in errors)

        if self._images_error is not None:
            self._images_error.setText(errors.get("images", ""))
            self._images_error.setVisible("images" in errors)

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _make_error_label() -> QLabel:
        lbl = QLabel()
        lbl.setFont(QFont(FONT_FAMILY, 12))
        lbl.setStyleSheet(f"color: {ERROR_COLOR}; background: transparent;")
        lbl.setVisible(False)
        return lbl
