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
    # Minimal 1x1 red PNG
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


def test_create_copies_files(dao: LocalTestDao, sample_image: Path):
    test = dao.create("My Test", cover_src=sample_image, image_srcs=[sample_image])

    assert test.name == "My Test"
    assert test.id  # non-empty
    assert dao.get_cover_path(test).is_file()
    assert dao.get_image_path(test, test.image_filenames[0]).is_file()


def test_create_generates_unique_id(dao: LocalTestDao, sample_image: Path):
    t1 = dao.create("A", cover_src=sample_image, image_srcs=[sample_image])
    t2 = dao.create("B", cover_src=sample_image, image_srcs=[sample_image])
    assert t1.id != t2.id


def test_load_all_after_create(dao: LocalTestDao, sample_image: Path):
    dao.create("A", cover_src=sample_image, image_srcs=[sample_image])
    dao.create("B", cover_src=sample_image, image_srcs=[sample_image])
    tests = dao.load_all()
    assert len(tests) == 2
    assert {t.name for t in tests} == {"A", "B"}


def test_load_by_id(dao: LocalTestDao, sample_image: Path):
    created = dao.create("X", cover_src=sample_image, image_srcs=[sample_image])
    loaded = dao.load(created.id)
    assert loaded is not None
    assert loaded.name == "X"
    assert loaded.id == created.id


def test_load_nonexistent(dao: LocalTestDao):
    assert dao.load("no-such-id") is None


def test_delete_removes_files_and_meta(dao: LocalTestDao, sample_image: Path):
    test = dao.create("Del", cover_src=sample_image, image_srcs=[sample_image])
    test_dir = dao.get_cover_path(test).parent
    assert test_dir.is_dir()

    dao.delete(test.id)
    assert not test_dir.exists()
    assert dao.load(test.id) is None
    assert dao.load_all() == []


def test_get_cover_path(dao: LocalTestDao, sample_image: Path):
    test = dao.create("C", cover_src=sample_image, image_srcs=[sample_image])
    cover = dao.get_cover_path(test)
    assert cover.name == f"cover{sample_image.suffix}"
    assert cover.is_file()


def test_get_image_path(dao: LocalTestDao, sample_image: Path):
    test = dao.create("I", cover_src=sample_image, image_srcs=[sample_image, sample_image])
    assert len(test.image_filenames) == 2
    for fn in test.image_filenames:
        assert dao.get_image_path(test, fn).is_file()


def test_load_all_empty(dao: LocalTestDao):
    assert dao.load_all() == []


def test_load_all_corrupt_json(dao: LocalTestDao):
    meta = dao._meta_path()
    meta.parent.mkdir(parents=True, exist_ok=True)
    meta.write_text("NOT VALID JSON!!!", encoding="utf-8")
    assert dao.load_all() == []


def test_cover_preserves_extension(dao: LocalTestDao, sample_jpg: Path):
    test = dao.create("Ext", cover_src=sample_jpg, image_srcs=[sample_jpg])
    assert test.cover_filename == "cover.jpg"


def test_image_filenames_numbered(dao: LocalTestDao, sample_image: Path):
    test = dao.create("Num", cover_src=sample_image, image_srcs=[sample_image, sample_image, sample_image])
    assert test.image_filenames == ["001.png", "002.png", "003.png"]


def test_update_changes_name(dao: LocalTestDao, sample_image: Path):
    test = dao.create("Old", cover_src=sample_image, image_srcs=[sample_image])
    updated = dao.update(test.id, "New", cover_src=sample_image, image_srcs=[sample_image])
    assert updated.name == "New"
    assert updated.id == test.id
    loaded = dao.load(test.id)
    assert loaded is not None
    assert loaded.name == "New"


def test_update_replaces_files(dao: LocalTestDao, sample_image: Path, sample_jpg: Path):
    test = dao.create("T", cover_src=sample_image, image_srcs=[sample_image])
    updated = dao.update(test.id, "T", cover_src=sample_jpg, image_srcs=[sample_jpg, sample_jpg])
    assert updated.cover_filename == "cover.jpg"
    assert len(updated.image_filenames) == 2
    assert dao.get_cover_path(updated).is_file()


def test_update_preserves_other_tests(dao: LocalTestDao, sample_image: Path):
    t1 = dao.create("A", cover_src=sample_image, image_srcs=[sample_image])
    t2 = dao.create("B", cover_src=sample_image, image_srcs=[sample_image])
    dao.update(t1.id, "A2", cover_src=sample_image, image_srcs=[sample_image])
    all_tests = dao.load_all()
    assert len(all_tests) == 2
    names = {t.name for t in all_tests}
    assert names == {"A2", "B"}
