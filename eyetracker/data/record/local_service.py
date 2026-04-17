"""Local filesystem implementation of RecordService."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict
from pathlib import Path

from eyetracker.data.record.service import (
    AoiStatsResult,
    Record,
    RecordListResult,
    RecordMetrics,
    RecordQuery,
    RecordService,
    RecordSummary,
    RoiStat,
)

logger = logging.getLogger(__name__)

_DEFAULT_DIR = Path.home() / ".eyetracker" / "records"


def _build_tge_histogram(values: list[float]) -> list[dict]:
    if not values:
        return []
    bin_width = 0.1
    max_val = max(values)
    n_bins = int(max_val / bin_width) + 1
    counts = [0] * n_bins
    for v in values:
        idx = min(int(v / bin_width), n_bins - 1)
        counts[idx] += 1
    return [
        {"binStart": round(i * bin_width, 1), "count": counts[i]}
        for i in range(n_bins)
    ]


class LocalRecordService(RecordService):
    """Saves records as JSON files in a local directory."""

    def __init__(self, base_dir: Path | None = None):
        self._base_dir = base_dir or _DEFAULT_DIR

    def save_unauthorized(self, record: Record, token: str, login: str) -> None:
        record.user_login = login
        self.save(record)

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

    def get_aoi_stats(self, test_id: str) -> AoiStatsResult:
        result = self.query(RecordQuery(test_id=test_id, page_size=10_000))
        stats: dict[str, list] = {}  # name -> [hits, total, color, first_fixation_required]
        tge_values: list[float] = []
        for summary in result.items:
            record = self.load(summary.id)
            if record is None:
                continue
            if record.metrics.tge is not None:
                tge_values.append(record.metrics.tge)
            for roi in record.metrics.roi_metrics:
                name = roi.get("name", "?")
                if name not in stats:
                    stats[name] = [0, 0, roi.get("color", "#0a84ff"), bool(roi.get("first_fixation_required"))]
                stats[name][1] += 1
                if roi.get("hit"):
                    stats[name][0] += 1
        aois = [
            RoiStat(name=name, color=v[2], hits=v[0], total=v[1], first_fixation_required=v[3])
            for name, v in stats.items()
        ]
        tge_histogram = _build_tge_histogram(tge_values)
        return AoiStatsResult(aois=aois, tge_histogram=tge_histogram)

    def is_aoi_sync_needed(self, test_id: str, aoi: list[dict]) -> bool:
        current_names = {r["name"] for r in aoi}
        result = self.query(RecordQuery(test_id=test_id, page_size=10_000))
        for summary in result.items:
            record = self.load(summary.id)
            if record is None:
                continue
            record_names = {r["name"] for r in record.metrics.roi_metrics}
            if current_names != record_names:
                return True
        return False

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
            hit_map: dict[str, bool] = {}
            for roi in record.metrics.roi_metrics:
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
            m = data.get("metrics", {})
            metrics = RecordMetrics(
                gaze_groups=m.get("gaze_groups", []),
                fixations=m.get("fixations", []),
                first_fixation_time_ms=m.get("first_fixation_time_ms"),
                saccades=m.get("saccades", []),
                roi_metrics=m.get("roi_metrics", []),
                aoi_sequence=m.get("aoi_sequence", []),
                tge=m.get("tge"),
            )
            return Record(
                id=data["id"],
                test_id=data["test_id"],
                user_login=data.get("user_login", ""),
                started_at=data["started_at"],
                finished_at=data["finished_at"],
                duration_ms=data["duration_ms"],
                metrics=metrics,
                created_at=data["created_at"],
            )
        except (json.JSONDecodeError, KeyError, OSError) as exc:
            logger.warning("Failed to read record from %s: %s", path, exc)
            return None
