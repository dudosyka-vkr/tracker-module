"""ZIP import: create a test from an exported ZIP file."""

from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path

from eyetracker.data.test.dao import TestDao, TestData


def import_test_zip(zip_path: Path, dao: TestDao) -> TestData:
    """Import a test from a ZIP produced by ``export_test_zip``.

    Extracts the archive to a temporary directory, reads ``test.json``,
    creates a new test via *dao*, saves ROI regions, and returns the
    newly created :class:`TestData`.

    Raises:
        zipfile.BadZipFile: if *zip_path* is not a valid ZIP.
        ValueError: if ``test.json`` is missing or structurally invalid.
        FileNotFoundError: if a referenced image file is absent in the ZIP.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            if "test.json" not in names:
                raise ValueError("test.json not found in ZIP")
            zf.extractall(tmp)

        meta = json.loads((tmp / "test.json").read_text(encoding="utf-8"))

        name: str = meta.get("name", "").strip()
        if not name:
            raise ValueError("test.json: 'name' field is missing or empty")

        cover_rel: str = meta.get("cover", "")
        if not cover_rel:
            raise ValueError("test.json: 'cover' field is missing")

        images_meta: list[dict] = meta.get("images", [])
        if not images_meta:
            raise ValueError("test.json: 'images' list is empty")

        def _resolve(rel: str) -> Path:
            # Strip leading ./ or /
            return tmp / rel.lstrip("./").lstrip("/")

        cover_path = _resolve(cover_rel)
        if not cover_path.is_file():
            raise FileNotFoundError(f"Cover image not found in ZIP: {cover_rel}")

        image_paths: list[Path] = []
        for entry in images_meta:
            p = _resolve(entry["path"])
            if not p.is_file():
                raise FileNotFoundError(f"Image not found in ZIP: {entry['path']}")
            image_paths.append(p)

        test = dao.create(name=name, cover_src=cover_path, image_srcs=image_paths)

        # Map newly assigned filenames back to ROI regions from the JSON
        regions: dict[str, list] = {}
        for i, entry in enumerate(images_meta):
            roi_list = entry.get("regions", [])
            if roi_list and i < len(test.image_filenames):
                regions[test.image_filenames[i]] = roi_list

        if regions:
            dao.save_regions(test.id, regions)
            reloaded = dao.load(test.id)
            if reloaded is not None:
                return reloaded

        return test
