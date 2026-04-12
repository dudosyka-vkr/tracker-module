"""Remote HTTP implementation of TestDao."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from eyetracker.data.http_client import ApiError, HttpClient
from eyetracker.data.test.dao import TestDao, TestData

logger = logging.getLogger(__name__)

_DEFAULT_CACHE = Path.home() / ".eyetracker" / "cache" / "tests"


class ApiTestDao(TestDao):
    """Fetches and stores tests via the backend REST API.

    Images are downloaded on demand and cached under ``~/.eyetracker/cache/tests/``.
    """

    def __init__(self, client: HttpClient, cache_dir: Path | None = None) -> None:
        self._client = client
        self._cache_dir = cache_dir or _DEFAULT_CACHE

    # -- public API -----------------------------------------------------------

    def create(self, name: str, image_src: Path) -> TestData:
        files = [("image", (image_src.name, image_src.read_bytes(), "application/octet-stream"))]
        resp = self._client.post("/tests", files=files, data={"name": name})
        return _parse_test(resp)

    def load_all(self) -> list[TestData]:
        try:
            resp = self._client.get("/tests")
        except ApiError:
            return []
        return [_parse_test(t) for t in resp.get("tests", [])]

    def load(self, test_id: str) -> TestData | None:
        try:
            resp = self._client.get(f"/tests/{test_id}")
        except ApiError:
            return None
        return _parse_test(resp)

    def update_name(self, test_id: str, name: str) -> TestData:
        self._client.patch(f"/tests/{test_id}/name", data={"name": name})
        return _parse_test(self._client.get(f"/tests/{test_id}"))

    def delete(self, test_id: str) -> None:
        self._client.delete(f"/tests/{test_id}")
        self._invalidate_cache(test_id)

    def get_image_path(self, test: TestData) -> Path:
        cache = self._cache_dir / test.id / "image"
        if not cache.is_file():
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(self._client.get_bytes(f"/tests/{test.id}/image"))
        return cache

    def save_aoi(self, test_id: str, aoi: list[dict]) -> None:
        self._client.patch(f"/tests/{test_id}/aoi", json={"aoi": aoi})

    def load_by_token(self, code: str) -> TestData | None:
        try:
            resp = self._client.get(f"/tests/by-token/{code}")
        except Exception:
            return None
        return _parse_test(resp)

    def get_token(self, test_id: str) -> str:
        resp = self._client.post(f"/tests/{test_id}/token")
        return resp["code"]

    def sync_aoi_metrics(self, test_id: str, record_service: object) -> None:
        self._client.post("/records/sync-aoi", params=[("testId", int(test_id))])

    # -- private helpers ------------------------------------------------------

    def _invalidate_cache(self, test_id: str) -> None:
        cache_dir = self._cache_dir / test_id
        if cache_dir.is_dir():
            shutil.rmtree(cache_dir)


def _parse_test(item: dict) -> TestData:
    return TestData(
        id=str(item["id"]),
        name=item["name"],
        image_filename="image",
        aoi=item.get("aoi", []),
        author=item.get("userLogin", ""),
    )
