"""Remote HTTP implementation of RecordService."""

from __future__ import annotations

from eyetracker.data.http_client import ApiError, HttpClient
from eyetracker.data.record.service import (
    Record,
    RecordItem,
    RecordItemMetrics,
    RecordListResult,
    RecordQuery,
    RecordService,
    RecordSummary,
    RoiStat,
)


class ApiRecordService(RecordService):
    """Persists and queries records via the backend REST API."""

    def __init__(self, client: HttpClient) -> None:
        self._client = client
        self._test_cache: dict[str, dict] = {}  # test_id -> cached test response

    # -- public API -----------------------------------------------------------

    def save(self, record: Record) -> None:
        test_resp = self._client.get(f"/tests/{record.test_id}")
        ids = _image_ids(test_resp)

        items = []
        for item in record.items:
            index = int(item.image_filename)
            items.append({
                "imageId": ids[index],
                "metrics": {
                    "gazeGroups": item.metrics.gaze_groups,
                    "fixations": item.metrics.fixations,
                    "firstFixationTimeMs": item.metrics.first_fixation_time_ms,
                    "saccades": item.metrics.saccades,
                    "roiMetrics": item.metrics.roi_metrics,
                },
            })

        self._client.post("/records", json={
            "testId": int(record.test_id),
            "startedAt": record.started_at,
            "finishedAt": record.finished_at,
            "durationMs": record.duration_ms,
            "items": items,
        })

    def save_unauthorized(self, record: Record, token: str, login: str) -> None:
        test_resp = self._client.get(f"/tests/by-token/{token}")
        ids = _image_ids(test_resp)

        items = []
        for item in record.items:
            index = int(item.image_filename)
            items.append({
                "imageId": ids[index],
                "metrics": {
                    "gazeGroups": item.metrics.gaze_groups,
                    "fixations": item.metrics.fixations,
                    "firstFixationTimeMs": item.metrics.first_fixation_time_ms,
                    "saccades": item.metrics.saccades,
                    "roiMetrics": item.metrics.roi_metrics,
                },
            })
        self._client.post("/records/unauthorized", json={
            "token": token,
            "login": login,
            "startedAt": record.started_at,
            "finishedAt": record.finished_at,
            "durationMs": record.duration_ms,
            "items": items,
        })

    def query(self, params: RecordQuery) -> RecordListResult:
        try:
            query_params = self._build_query_params(params)
            resp = self._client.get("/records", params=query_params)
        except ApiError:
            return RecordListResult(items=[], page=params.page, page_size=params.page_size, total=0)
        summaries = [_parse_summary(item) for item in resp["items"]]
        return RecordListResult(
            items=summaries,
            page=resp["page"],
            page_size=resp["pageSize"],
            total=resp["total"],
        )

    def load(self, record_id: str) -> Record | None:
        try:
            resp = self._client.get(f"/records/{record_id}")
        except ApiError:
            return None

        test_id_key = str(resp["testId"])
        if test_id_key not in self._test_cache:
            self._test_cache[test_id_key] = self._client.get(f"/tests/{test_id_key}")
        test_resp = self._test_cache[test_id_key]
        ids = _image_ids(test_resp)

        items = []
        for item_data in resp["items"]:
            image_id = item_data["imageId"]
            try:
                image_index = ids.index(image_id)
            except ValueError:
                image_index = 0
            m = item_data.get("metrics", {})
            items.append(RecordItem(
                image_filename=str(image_index),
                image_index=image_index,
                metrics=RecordItemMetrics(
                    gaze_groups=m.get("gazeGroups", []),
                    fixations=m.get("fixations", []),
                    first_fixation_time_ms=m.get("firstFixationTimeMs"),
                    saccades=m.get("saccades", []),
                    roi_metrics=m.get("roiMetrics", []),
                ),
            ))

        return Record(
            id=str(resp["id"]),
            test_id=str(resp["testId"]),
            user_login=resp["userLogin"],
            started_at=resp["startedAt"],
            finished_at=resp["finishedAt"],
            duration_ms=resp["durationMs"],
            items=items,
            created_at=resp["createdAt"],
        )

    def get_roi_stats(self, test_id: str) -> list[RoiStat]:
        try:
            resp = self._client.get(f"/tests/{test_id}/roi-stats")
        except Exception:
            return []
        return [
            RoiStat(
                name=r["name"],
                color=r.get("color", "#0a84ff"),
                hits=r["hits"],
                total=r["total"],
                first_fixation_required=r.get("firstFixationRequired", False),
            )
            for r in resp.get("rois", [])
        ]

    def is_roi_sync_needed(self, test_id: str, image_regions: dict) -> bool:
        try:
            resp = self._client.get("/records/roi-sync", params=[("testId", int(test_id))])
            return not resp.get("synced", True)
        except Exception:
            return False

    def suggest_users(self, params: RecordQuery) -> list[str]:
        try:
            query_params = self._build_query_params(params, skip_user_fields=True)
            resp = self._client.get("/records/users/suggest", params=query_params)
        except ApiError:
            return []
        return resp["items"]

    # -- private helpers ------------------------------------------------------

    def _build_query_params(
        self, params: RecordQuery, skip_user_fields: bool = False
    ) -> list[tuple]:
        result: list[tuple] = []

        if params.test_id is not None:
            result.append(("testId", int(params.test_id)))
        if not skip_user_fields:
            if params.user_login is not None:
                result.append(("userLogin", params.user_login))
            if params.user_login_contains is not None:
                result.append(("userLoginContains", params.user_login_contains))
        if params.date_from is not None:
            result.append(("from", params.date_from))
        if params.date_to is not None:
            result.append(("to", params.date_to))
        if params.roi_hits:
            for name, hit in params.roi_hits.items():
                result.append((f"roi.{name}", str(hit).lower()))
        result.append(("page", params.page))
        result.append(("pageSize", params.page_size))

        return result


def _image_ids(test_resp: dict) -> list[int]:
    images = sorted(test_resp.get("images", []), key=lambda img: img.get("sortOrder", 0))
    return [img["id"] for img in images]


def _parse_summary(item: dict) -> RecordSummary:
    return RecordSummary(
        id=str(item["id"]),
        test_id=str(item["testId"]),
        user_login=item["userLogin"],
        started_at=item["startedAt"],
        finished_at=item["finishedAt"],
        duration_ms=item["durationMs"],
        created_at=item["createdAt"],
        roi_hits=item.get("roiHits", []),
    )
