"""Tests for export_test_zip."""

import json
import struct
import zipfile
import zlib
from pathlib import Path

import pytest

from eyetracker.data.test import LocalTestDao
from eyetracker.data.test.export import export_test_zip


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def dao(tmp_path: Path) -> LocalTestDao:
    return LocalTestDao(base_dir=tmp_path / "tests")


@pytest.fixture()
def sample_image(tmp_path: Path) -> Path:
    """Minimal valid 1×1 PNG."""
    def _chunk(tag: bytes, data: bytes) -> bytes:
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    idat = _chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00"))
    iend = _chunk(b"IEND", b"")
    path = tmp_path / "img.png"
    path.write_bytes(sig + ihdr + idat + iend)
    return path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_zip_json(dest: Path) -> dict:
    with zipfile.ZipFile(dest) as zf:
        return json.loads(zf.read("test.json"))


def _zip_names(dest: Path) -> set[str]:
    with zipfile.ZipFile(dest) as zf:
        return set(zf.namelist())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_zip_contains_images_and_json(dao, sample_image, tmp_path):
    test = dao.create("MyTest", sample_image, [sample_image, sample_image])
    dest = tmp_path / "out.zip"
    export_test_zip(test, dao, dest)

    names = _zip_names(dest)
    assert "test.json" in names
    assert test.cover_filename in names
    for fn in test.image_filenames:
        assert fn in names


def test_json_name_and_cover(dao, sample_image, tmp_path):
    test = dao.create("Export Test", sample_image, [sample_image])
    dest = tmp_path / "out.zip"
    export_test_zip(test, dao, dest)

    data = _read_zip_json(dest)
    assert data["name"] == "Export Test"
    assert data["cover"] == f"./{test.cover_filename}"


def test_json_image_paths_are_relative(dao, sample_image, tmp_path):
    test = dao.create("T", sample_image, [sample_image, sample_image])
    dest = tmp_path / "out.zip"
    export_test_zip(test, dao, dest)

    data = _read_zip_json(dest)
    assert len(data["images"]) == 2
    for entry, filename in zip(data["images"], test.image_filenames):
        assert entry["path"] == f"./{filename}"


def test_json_includes_regions(dao, sample_image, tmp_path):
    test = dao.create("T", sample_image, [sample_image])
    regions = {
        test.image_filenames[0]: [
            {
                "name": "Zone A",
                "color": "#ff0000",
                "first_fixation": True,
                "points": [{"x": 0.1, "y": 0.1}, {"x": 0.5, "y": 0.1}, {"x": 0.3, "y": 0.5}],
            }
        ]
    }
    dao.save_regions(test.id, regions)
    test = dao.load(test.id)
    dest = tmp_path / "out.zip"
    export_test_zip(test, dao, dest)

    data = _read_zip_json(dest)
    exported_regions = data["images"][0]["regions"]
    assert len(exported_regions) == 1
    assert exported_regions[0]["name"] == "Zone A"
    assert exported_regions[0]["first_fixation"] is True
    assert exported_regions[0]["color"] == "#ff0000"
    assert len(exported_regions[0]["points"]) == 3


def test_json_empty_regions_for_image_without_rois(dao, sample_image, tmp_path):
    test = dao.create("T", sample_image, [sample_image])
    dest = tmp_path / "out.zip"
    export_test_zip(test, dao, dest)

    data = _read_zip_json(dest)
    assert data["images"][0]["regions"] == []


def test_export_multiple_images_order_preserved(dao, sample_image, tmp_path):
    test = dao.create("T", sample_image, [sample_image, sample_image, sample_image])
    dest = tmp_path / "out.zip"
    export_test_zip(test, dao, dest)

    data = _read_zip_json(dest)
    paths = [e["path"] for e in data["images"]]
    expected = [f"./{fn}" for fn in test.image_filenames]
    assert paths == expected
