"""Local filesystem implementation of TestDao."""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from eyetracker.data.record.service import RecordQuery, RecordService
from eyetracker.data.test.dao import TestDao, TestData

logger = logging.getLogger(__name__)

_DEFAULT_BASE = Path.home() / ".eyetracker" / "tests"


class LocalTestDao(TestDao):
    """Store tests as directories under ``~/.eyetracker/tests/<id>/``."""

    def __init__(self, base_dir: Path | None = None):
        self._base = base_dir or _DEFAULT_BASE

    # -- public API ----------------------------------------------------------

    def create(self, name: str, image_src: Path) -> TestData:
        test_id = uuid4().hex[:12]
        test_dir = self._base / test_id
        test_dir.mkdir(parents=True, exist_ok=True)

        image_filename = f"image{image_src.suffix}"
        shutil.copy2(image_src, test_dir / image_filename)

        test = TestData(
            id=test_id,
            name=name,
            image_filename=image_filename,
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
            return [TestData(**{**{"aoi": []}, **item}) for item in raw]
        except (json.JSONDecodeError, OSError, TypeError, KeyError) as exc:
            logger.warning("Failed to load tests meta: %s", exc)
            return []

    def load(self, test_id: str) -> TestData | None:
        return next((t for t in self.load_all() if t.id == test_id), None)

    def update_name(self, test_id: str, name: str) -> TestData:
        test = self.load(test_id)
        if test is None:
            raise FileNotFoundError(test_id)
        updated = TestData(
            id=test_id,
            name=name,
            image_filename=test.image_filename,
            aoi=test.aoi,
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

    def get_image_path(self, test: TestData) -> Path:
        return self._base / test.id / test.image_filename

    def save_aoi(self, test_id: str, aoi: list[dict]) -> None:
        tests = self.load_all()
        for t in tests:
            if t.id == test_id:
                t.aoi = aoi
                break
        self._save_meta(tests)

    def load_by_token(self, code: str) -> TestData | None:
        raise NotImplementedError("Token lookup is not supported in local mode")

    def get_token(self, test_id: str) -> str:
        raise NotImplementedError("Token generation is not supported in local mode")

    def sync_aoi_metrics(self, test_id: str, record_service: RecordService) -> None:
        test = self.load(test_id)
        if test is None:
            return
        from eyetracker.core.roi import compute_roi_metrics
        result = record_service.query(RecordQuery(test_id=test_id, page_size=10_000))
        for summary in result.items:
            record = record_service.load(summary.id)
            if record is None:
                continue
            record.metrics.roi_metrics = compute_roi_metrics(
                test.aoi, record.metrics.fixations,
            )
            record_service.save(record)

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
