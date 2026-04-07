"""Remote HTTP implementation of TestDao."""

from __future__ import annotations

import json
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

    def create(self, name: str, cover_src: Path, image_srcs: list[Path]) -> TestData:
        files = [("cover", (cover_src.name, cover_src.read_bytes(), "application/octet-stream"))]
        files += [
            ("images", (s.name, s.read_bytes(), "application/octet-stream"))
            for s in image_srcs
        ]
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

    def update(
        self, test_id: str, name: str, cover_src: Path, image_srcs: list[Path]
    ) -> TestData:
        files = [("cover", (cover_src.name, cover_src.read_bytes(), "application/octet-stream"))]
        files += [
            ("images", (s.name, s.read_bytes(), "application/octet-stream"))
            for s in image_srcs
        ]
        resp = self._client.put(f"/tests/{test_id}", files=files, data={"name": name})
        self._invalidate_cache(test_id)
        return _parse_test(resp)

    def delete(self, test_id: str) -> None:
        self._client.delete(f"/tests/{test_id}")
        self._invalidate_cache(test_id)

    def get_cover_path(self, test: TestData) -> Path:
        cache = self._cache_dir / test.id / "cover"
        if not cache.is_file():
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(self._client.get_bytes(f"/tests/{test.id}/cover"))
        return cache

    def get_image_path(self, test: TestData, filename: str) -> Path:
        """``filename`` is a string index (``"0"``, ``"1"``, …) matching ``image_filenames``."""
        cache = self._cache_dir / test.id / filename
        if not cache.is_file():
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(
                self._client.get_bytes(f"/tests/{test.id}/images/{filename}")
            )
        return cache

    def save_regions(self, test_id: str, regions: dict[str, list[dict]]) -> None:
        test_resp = self._client.get(f"/tests/{test_id}")
        image_ids: list[int] = test_resp["imageIds"]
        for filename, roi_list in regions.items():
            image_id = image_ids[int(filename)]
            self._client.patch(
                f"/tests/images/{image_id}/roi",
                json={"roi": json.dumps(roi_list, ensure_ascii=False)},
            )

    def sync_roi_metrics(self, test_id: str, record_service: object) -> None:
        self._client.post(f"/tests/{test_id}/sync-roi")

    # -- private helpers ------------------------------------------------------

    def _invalidate_cache(self, test_id: str) -> None:
        cache_dir = self._cache_dir / test_id
        if cache_dir.is_dir():
            shutil.rmtree(cache_dir)


def _parse_test(item: dict) -> TestData:
    count = len(item.get("imageUrls", []))
    return TestData(
        id=str(item["id"]),
        name=item["name"],
        cover_filename="cover",
        image_filenames=[str(i) for i in range(count)],
        image_regions={},
    )
