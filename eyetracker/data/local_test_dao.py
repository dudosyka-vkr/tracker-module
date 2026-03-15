"""Local filesystem implementation of TestDao."""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from eyetracker.data.test_dao import TestDao, TestData

logger = logging.getLogger(__name__)

_DEFAULT_BASE = Path.home() / ".eyetracker" / "tests"


class LocalTestDao(TestDao):
    """Store tests as directories under ``~/.eyetracker/tests/<id>/``."""

    def __init__(self, base_dir: Path | None = None):
        self._base = base_dir or _DEFAULT_BASE

    # -- public API ----------------------------------------------------------

    def create(self, name: str, cover_src: Path, image_srcs: list[Path]) -> TestData:
        test_id = uuid4().hex[:12]
        test_dir = self._base / test_id
        test_dir.mkdir(parents=True, exist_ok=True)

        cover_filename = f"cover{cover_src.suffix}"
        shutil.copy2(cover_src, test_dir / cover_filename)

        image_filenames: list[str] = []
        for i, src in enumerate(image_srcs, start=1):
            fname = f"{i:03d}{src.suffix}"
            shutil.copy2(src, test_dir / fname)
            image_filenames.append(fname)

        test = TestData(
            id=test_id,
            name=name,
            cover_filename=cover_filename,
            image_filenames=image_filenames,
        )
        self._append_meta(test)
        return test

    def load_all(self) -> list[TestData]:
        meta_path = self._meta_path()
        if not meta_path.is_file():
            return []
        try:
            raw = json.loads(meta_path.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                return []
            return [TestData(**item) for item in raw]
        except (json.JSONDecodeError, OSError, TypeError, KeyError) as exc:
            logger.warning("Failed to load tests meta: %s", exc)
            return []

    def load(self, test_id: str) -> TestData | None:
        return next((t for t in self.load_all() if t.id == test_id), None)

    def update(self, test_id: str, name: str, cover_src: Path, image_srcs: list[Path]) -> TestData:
        test_dir = self._base / test_id
        tmp_dir = self._base / f"{test_id}_tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)

        cover_filename = f"cover{cover_src.suffix}"
        shutil.copy2(cover_src, tmp_dir / cover_filename)

        image_filenames: list[str] = []
        for i, src in enumerate(image_srcs, start=1):
            fname = f"{i:03d}{src.suffix}"
            shutil.copy2(src, tmp_dir / fname)
            image_filenames.append(fname)

        if test_dir.is_dir():
            shutil.rmtree(test_dir)
        tmp_dir.rename(test_dir)

        updated = TestData(
            id=test_id,
            name=name,
            cover_filename=cover_filename,
            image_filenames=image_filenames,
        )
        tests = [updated if t.id == test_id else t for t in self.load_all()]
        self._save_meta(tests)
        return updated

    def delete(self, test_id: str) -> None:
        tests = [t for t in self.load_all() if t.id != test_id]
        self._save_meta(tests)
        test_dir = self._base / test_id
        if test_dir.is_dir():
            shutil.rmtree(test_dir)

    def get_cover_path(self, test: TestData) -> Path:
        return self._base / test.id / test.cover_filename

    def get_image_path(self, test: TestData, filename: str) -> Path:
        return self._base / test.id / filename

    # -- private helpers -----------------------------------------------------

    def _meta_path(self) -> Path:
        return self._base / "tests.json"

    def _append_meta(self, test: TestData) -> None:
        tests = self.load_all()
        tests.append(test)
        self._save_meta(tests)

    def _save_meta(self, tests: list[TestData]) -> None:
        self._base.mkdir(parents=True, exist_ok=True)
        try:
            self._meta_path().write_text(
                json.dumps([asdict(t) for t in tests], indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("Failed to save tests meta: %s", exc)
