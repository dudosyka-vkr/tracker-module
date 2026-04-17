"""Tests for LocalTestDao."""

import json
from pathlib import Path

import pytest

from eyetracker.data.test import LocalTestDao


@pytest.fixture()
def dao(tmp_path: Path) -> LocalTestDao:
    return LocalTestDao(base_dir=tmp_path / "tests")


@pytest.fixture()
def sample_image(tmp_path: Path) -> Path:
    """Create a tiny valid PNG file."""
    import struct
    import zlib

    def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
        c = chunk_type + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = _png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    raw = zlib.compress(b"\x00\xff\x00\x00")
    idat = _png_chunk(b"IDAT", raw)
    iend = _png_chunk(b"IEND", b"")

    img = tmp_path / "sample.png"
    img.write_bytes(sig + ihdr + idat + iend)
    return img


@pytest.fixture()
def sample_jpg(tmp_path: Path) -> Path:
    img = tmp_path / "photo.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 20)
    return img


def test_create_copies_file(dao: LocalTestDao, sample_image: Path):
    test = dao.create("My Test", image_src=sample_image)

    assert test.name == "My Test"
    assert test.id  # non-empty
    assert dao.get_image_path(test).is_file()


def test_create_generates_unique_id(dao: LocalTestDao, sample_image: Path):
    t1 = dao.create("A", image_src=sample_image)
    t2 = dao.create("B", image_src=sample_image)
    assert t1.id != t2.id


def test_load_all_after_create(dao: LocalTestDao, sample_image: Path):
    dao.create("A", image_src=sample_image)
    dao.create("B", image_src=sample_image)
    tests = dao.load_all()
    assert len(tests) == 2
    assert {t.name for t in tests} == {"A", "B"}


def test_load_by_id(dao: LocalTestDao, sample_image: Path):
    created = dao.create("X", image_src=sample_image)
    loaded = dao.load(created.id)
    assert loaded is not None
    assert loaded.name == "X"
    assert loaded.id == created.id


def test_load_nonexistent(dao: LocalTestDao):
    assert dao.load("no-such-id") is None


def test_delete_removes_files_and_meta(dao: LocalTestDao, sample_image: Path):
    test = dao.create("Del", image_src=sample_image)
    test_dir = dao.get_image_path(test).parent
    assert test_dir.is_dir()

    dao.delete(test.id)
    assert not test_dir.exists()
    assert dao.load(test.id) is None
    assert dao.load_all() == []


def test_get_image_path(dao: LocalTestDao, sample_image: Path):
    test = dao.create("I", image_src=sample_image)
    assert dao.get_image_path(test).is_file()


def test_load_all_empty(dao: LocalTestDao):
    assert dao.load_all() == []


def test_load_all_corrupt_json(dao: LocalTestDao):
    meta = dao._meta_path()
    meta.parent.mkdir(parents=True, exist_ok=True)
    meta.write_text("NOT VALID JSON!!!", encoding="utf-8")
    assert dao.load_all() == []


def test_image_preserves_extension(dao: LocalTestDao, sample_jpg: Path):
    test = dao.create("Ext", image_src=sample_jpg)
    assert test.image_filename.endswith(".jpg")


def test_update_name(dao: LocalTestDao, sample_image: Path):
    test = dao.create("Old", image_src=sample_image)
    updated = dao.update_name(test.id, "New")
    assert updated.name == "New"
    assert updated.id == test.id
    loaded = dao.load(test.id)
    assert loaded is not None
    assert loaded.name == "New"


def test_save_aoi(dao: LocalTestDao, sample_image: Path):
    test = dao.create("T1", image_src=sample_image)
    aoi = [
        {"name": "Area1", "points": [{"x": 0.1, "y": 0.1}, {"x": 0.5, "y": 0.1}, {"x": 0.3, "y": 0.5}]},
    ]
    dao.save_aoi(test.id, aoi)
    reloaded = dao.load(test.id)
    assert reloaded is not None
    assert reloaded.aoi == aoi


def test_load_old_test_without_aoi_field(dao: LocalTestDao, sample_image: Path):
    test = dao.create("T2", image_src=sample_image)
    meta_path = dao._meta_path()
    data = json.loads(meta_path.read_text())
    for item in data:
        item.pop("aoi", None)
    meta_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    reloaded = dao.load(test.id)
    assert reloaded is not None
    assert reloaded.aoi == []
