"""Tests for import_test_zip."""

import json
import struct
import zipfile
import zlib
from pathlib import Path

import pytest

from eyetracker.data.test import LocalTestDao
from eyetracker.data.test.import_zip import import_test_zip


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def dao(tmp_path: Path) -> LocalTestDao:
    return LocalTestDao(base_dir=tmp_path / "tests")


@pytest.fixture()
def sample_png(tmp_path: Path) -> Path:
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


def _make_zip(dest: Path, name: str, cover: Path, images: list[Path], regions: dict | None = None) -> Path:
    """Build a ZIP in the same format as export_test_zip."""
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        cover_filename = f"cover{cover.suffix}"
        zf.write(cover, cover_filename)

        imgs_meta = []
        for i, img in enumerate(images, start=1):
            fname = f"{i:03d}{img.suffix}"
            zf.write(img, fname)
            roi_list = (regions or {}).get(fname, [])
            imgs_meta.append({"path": f"./{fname}", "regions": roi_list})

        meta = {
            "name": name,
            "cover": f"./{cover_filename}",
            "images": imgs_meta,
        }
        zf.writestr("test.json", json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
    return dest


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_import_creates_test(dao, sample_png, tmp_path):
    zip_path = _make_zip(tmp_path / "t.zip", "My Test", sample_png, [sample_png])
    test = import_test_zip(zip_path, dao)

    assert test.name == "My Test"
    assert test.cover_filename.startswith("cover")
    assert len(test.image_filenames) == 1


def test_import_test_is_persisted(dao, sample_png, tmp_path):
    zip_path = _make_zip(tmp_path / "t.zip", "Saved", sample_png, [sample_png])
    test = import_test_zip(zip_path, dao)

    loaded = dao.load(test.id)
    assert loaded is not None
    assert loaded.name == "Saved"


def test_import_images_are_copied(dao, sample_png, tmp_path):
    zip_path = _make_zip(tmp_path / "t.zip", "T", sample_png, [sample_png, sample_png])
    test = import_test_zip(zip_path, dao)

    for fn in test.image_filenames:
        assert dao.get_image_path(test, fn).is_file()
    assert dao.get_cover_path(test).is_file()


def test_import_preserves_image_count(dao, sample_png, tmp_path):
    zip_path = _make_zip(tmp_path / "t.zip", "T", sample_png, [sample_png, sample_png, sample_png])
    test = import_test_zip(zip_path, dao)
    assert len(test.image_filenames) == 3


def test_import_with_regions(dao, sample_png, tmp_path):
    regions = {
        "001.png": [
            {
                "name": "Zone A",
                "color": "#ff0000",
                "first_fixation": True,
                "points": [{"x": 0.1, "y": 0.1}, {"x": 0.5, "y": 0.1}, {"x": 0.3, "y": 0.5}],
            }
        ]
    }
    zip_path = _make_zip(tmp_path / "t.zip", "T", sample_png, [sample_png], regions=regions)
    test = import_test_zip(zip_path, dao)

    fn = test.image_filenames[0]
    assert fn in test.image_regions
    assert len(test.image_regions[fn]) == 1
    assert test.image_regions[fn][0]["name"] == "Zone A"
    assert test.image_regions[fn][0]["first_fixation"] is True


def test_import_no_regions_defaults_to_empty(dao, sample_png, tmp_path):
    zip_path = _make_zip(tmp_path / "t.zip", "T", sample_png, [sample_png])
    test = import_test_zip(zip_path, dao)
    assert test.image_regions == {}


def test_import_missing_test_json_raises(dao, sample_png, tmp_path):
    dest = tmp_path / "bad.zip"
    with zipfile.ZipFile(dest, "w") as zf:
        zf.write(sample_png, "img.png")
    with pytest.raises(ValueError, match="test.json"):
        import_test_zip(dest, dao)


def test_import_empty_name_raises(dao, sample_png, tmp_path):
    dest = tmp_path / "bad.zip"
    with zipfile.ZipFile(dest, "w") as zf:
        zf.write(sample_png, "cover.png")
        meta = {"name": "", "cover": "./cover.png", "images": [{"path": "./cover.png", "regions": []}]}
        zf.writestr("test.json", json.dumps(meta))
    with pytest.raises(ValueError, match="name"):
        import_test_zip(dest, dao)


def test_import_bad_zip_raises(tmp_path):
    dest = tmp_path / "bad.zip"
    dest.write_bytes(b"not a zip file")
    from zipfile import BadZipFile
    with pytest.raises(BadZipFile):
        from eyetracker.data.test import LocalTestDao
        dao = LocalTestDao(base_dir=tmp_path / "tests")
        import_test_zip(dest, dao)
