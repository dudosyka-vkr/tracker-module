"""Local filesystem implementation of RecordService."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict
from pathlib import Path

from eyetracker.data.record.service import (
    Record,
    RecordItem,
    RecordItemMetrics,
    RecordListResult,
    RecordQuery,
    RecordService,
    RecordSummary,
)

logger = logging.getLogger(__name__)

_DEFAULT_DIR = Path.home() / ".eyetracker" / "records"


class LocalRecordService(RecordService):
    """Saves records as JSON files in a local directory."""

    def __init__(self, base_dir: Path | None = None):
        self._base_dir = base_dir or _DEFAULT_DIR

    def save(self, record: Record) -> None:
        os.makedirs(self._base_dir, exist_ok=True)
        path = self._base_dir / f"{record.id}.json"
        path.write_text(
            json.dumps(asdict(record), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def query(self, params: RecordQuery) -> RecordListResult:
        summaries = self._load_all_summaries()

        if params.test_id is not None:
            summaries = [s for s in summaries if s.test_id == params.test_id]
        if params.user_login is not None:
            summaries = [s for s in summaries if s.user_login == params.user_login]
        if params.user_login_contains is not None:
            needle = params.user_login_contains.lower()
            summaries = [s for s in summaries if needle in s.user_login.lower()]
        if params.date_from is not None:
            summaries = [s for s in summaries if s.started_at >= params.date_from]
        if params.date_to is not None:
            summaries = [s for s in summaries if s.started_at <= params.date_to]
        if params.roi_hits:
            summaries = self._filter_by_roi(summaries, params.roi_hits)

        summaries.sort(key=lambda s: s.created_at, reverse=True)
        total = len(summaries)

        start = (params.page - 1) * params.page_size
        end = start + params.page_size
        page_items = summaries[start:end]

        return RecordListResult(
            items=page_items,
            page=params.page,
            page_size=params.page_size,
            total=total,
        )

    def load(self, record_id: str) -> Record | None:
        path = self._base_dir / f"{record_id}.json"
        if not path.is_file():
            return None
        return self._read_record(path)

    def suggest_users(self, params: RecordQuery) -> list[str]:
        neutral = RecordQuery(
            test_id=params.test_id,
            date_from=params.date_from,
            date_to=params.date_to,
            roi_hits=params.roi_hits,
            page_size=10_000,
        )
        result = self.query(neutral)
        return sorted({s.user_login for s in result.items if s.user_login})

    def _filter_by_roi(
        self, summaries: list[RecordSummary], roi_hits: dict[str, bool]
    ) -> list[RecordSummary]:
        result = []
        for summary in summaries:
            record = self.load(summary.id)
            if record is None:
                continue
            # Aggregate: was each named ROI hit in any image of this record?
            hit_map: dict[str, bool] = {}
            for item in record.items:
                for roi in item.metrics.roi_metrics:
                    name = roi.get("name", "")
                    hit_map[name] = hit_map.get(name, False) or bool(roi.get("hit"))
            if all(hit_map.get(name, False) == required for name, required in roi_hits.items()):
                result.append(summary)
        return result

    def _load_all_summaries(self) -> list[RecordSummary]:
        if not self._base_dir.is_dir():
            return []
        result: list[RecordSummary] = []
        for path in self._base_dir.glob("*.json"):
            summary = self._read_summary(path)
            if summary is not None:
                result.append(summary)
        return result

    @staticmethod
    def _read_summary(path: Path) -> RecordSummary | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return RecordSummary(
                id=data["id"],
                test_id=data["test_id"],
                user_login=data.get("user_login", ""),
                started_at=data["started_at"],
                finished_at=data["finished_at"],
                duration_ms=data["duration_ms"],
                created_at=data["created_at"],
            )
        except (json.JSONDecodeError, KeyError, OSError) as exc:
            logger.warning("Failed to read record summary from %s: %s", path, exc)
            return None

    @staticmethod
    def _read_record(path: Path) -> Record | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            items = [
                RecordItem(
                    image_filename=it["image_filename"],
                    image_index=it["image_index"],
                    metrics=RecordItemMetrics(
                        gaze_groups=it["metrics"]["gaze_groups"],
                        fixations=it["metrics"].get("fixations", []),
                        first_fixation_time_ms=it["metrics"].get("first_fixation_time_ms"),
                        saccades=it["metrics"].get("saccades", []),
                        roi_metrics=it["metrics"].get("roi_metrics", []),
                    ),
                )
                for it in data["items"]
            ]
            return Record(
                id=data["id"],
                test_id=data["test_id"],
                user_login=data.get("user_login", ""),
                started_at=data["started_at"],
                finished_at=data["finished_at"],
                duration_ms=data["duration_ms"],
                items=items,
                created_at=data["created_at"],
            )
        except (json.JSONDecodeError, KeyError, OSError) as exc:
            logger.warning("Failed to read record from %s: %s", path, exc)
            return None
