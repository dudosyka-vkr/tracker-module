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
    creates a new test via *dao*, saves AOI, and returns the
    newly created :class:`TestData`.

    Raises:
        zipfile.BadZipFile: if *zip_path* is not a valid ZIP.
        ValueError: if ``test.json`` is missing or structurally invalid.
        FileNotFoundError: if the referenced image file is absent in the ZIP.
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

        image_rel: str = meta.get("image", "")
        if not image_rel:
            raise ValueError("test.json: 'image' field is missing")

        def _resolve(rel: str) -> Path:
            # Strip leading ./ or /
            return tmp / rel.lstrip("./").lstrip("/")

        image_path = _resolve(image_rel)
        if not image_path.is_file():
            raise FileNotFoundError(f"Image not found in ZIP: {image_rel}")

        test = dao.create(name=name, image_src=image_path)

        aoi = meta.get("aoi", [])
        if aoi:
            dao.save_aoi(test.id, aoi)
            reloaded = dao.load(test.id)
            if reloaded is not None:
                return reloaded

        return test
