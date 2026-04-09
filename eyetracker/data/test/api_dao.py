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

    def create(self, name: str, cover_src: Path, image_srcs: list[Path]) -> TestData:
        # Step 1: create test with name + cover only
        files = [("cover", (cover_src.name, cover_src.read_bytes(), "application/octet-stream"))]
        resp = self._client.post("/tests", files=files, data={"name": name})
        test_id = str(resp["id"])

        # Step 2: upload images one by one in order
        for src in image_srcs:
            self._client.post(
                f"/tests/{test_id}/images",
                files=[("image", (src.name, src.read_bytes(), "application/octet-stream"))],
            )

        return _parse_test(self._client.get(f"/tests/{test_id}"))

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
        # Delete all existing images so we can re-upload in the new order
        current = self._client.get(f"/tests/{test_id}")
        for img in current.get("images", []):
            self._client.delete(f"/tests/images/{img['id']}")

        # Update name + cover
        files = [("cover", (cover_src.name, cover_src.read_bytes(), "application/octet-stream"))]
        self._client.put(f"/tests/{test_id}", files=files, data={"name": name})

        # Re-upload images in the correct order
        for src in image_srcs:
            self._client.post(
                f"/tests/{test_id}/images",
                files=[("image", (src.name, src.read_bytes(), "application/octet-stream"))],
            )

        self._invalidate_cache(test_id)
        return _parse_test(self._client.get(f"/tests/{test_id}"))

    def add_image(self, test_id: str, src: Path) -> TestData:
        self._client.post(
            f"/tests/{test_id}/images",
            files=[("image", (src.name, src.read_bytes(), "application/octet-stream"))],
        )
        self._invalidate_cache(test_id)
        return _parse_test(self._client.get(f"/tests/{test_id}"))

    def update_name(self, test_id: str, name: str) -> TestData:
        self._client.patch(f"/tests/{test_id}/name", data={"name": name})
        return _parse_test(self._client.get(f"/tests/{test_id}"))

    def update_cover(self, test_id: str, cover_src: Path) -> TestData:
        self._client.patch(
            f"/tests/{test_id}/cover",
            files=[("cover", (cover_src.name, cover_src.read_bytes(), "application/octet-stream"))],
        )
        self._invalidate_cache(test_id)
        return _parse_test(self._client.get(f"/tests/{test_id}"))

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
        images = _sorted_images(test_resp)
        for filename, roi_list in regions.items():
            idx = int(filename)
            if idx < len(images):
                self._client.patch(
                    f"/tests/images/{images[idx]['id']}/roi",
                    json={"rois": roi_list},
                )

    def load_by_token(self, code: str) -> TestData | None:
        try:
            resp = self._client.get(f"/tests/by-token/{code}")
        except Exception:
            return None
        return _parse_test(resp)

    def get_token(self, test_id: str) -> str:
        resp = self._client.post(f"/tests/{test_id}/token")
        return resp["code"]

    def sync_roi_metrics(self, test_id: str, record_service: object) -> None:
        self._client.post(f"/tests/{test_id}/sync-roi")

    # -- private helpers ------------------------------------------------------

    def _invalidate_cache(self, test_id: str) -> None:
        cache_dir = self._cache_dir / test_id
        if cache_dir.is_dir():
            shutil.rmtree(cache_dir)


def _sorted_images(item: dict) -> list[dict]:
    return sorted(item.get("images", []), key=lambda img: img.get("sortOrder", 0))


def _parse_test(item: dict) -> TestData:
    images = _sorted_images(item)
    image_regions: dict = {}
    for i, img in enumerate(images):
        rois = img.get("rois", [])
        if rois:
            image_regions[str(i)] = rois
    return TestData(
        id=str(item["id"]),
        name=item["name"],
        cover_filename="cover",
        image_filenames=[str(i) for i in range(len(images))],
        image_regions=image_regions,
    )
