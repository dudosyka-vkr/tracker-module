"""Tests for draft cache."""

from pathlib import Path

from eyetracker.data.draft_cache import DraftCache, DraftData


def _sample_draft(**kwargs) -> DraftData:
    defaults = {
        "draft_type": "create",
        "test_id": None,
        "name": "My Test",
        "cover_path": "/tmp/cover.png",
        "image_paths": ["/tmp/img1.png", "/tmp/img2.png"],
    }
    defaults.update(kwargs)
    return DraftData(**defaults)


def test_save_and_load(tmp_path: Path):
    path = tmp_path / "draft.json"
    cache = DraftCache(path=path)
    draft = _sample_draft()
    cache.save(draft)

    loaded = cache.load()
    assert loaded is not None
    assert loaded.draft_type == "create"
    assert loaded.test_id is None
    assert loaded.name == "My Test"
    assert loaded.cover_path == "/tmp/cover.png"
    assert loaded.image_paths == ["/tmp/img1.png", "/tmp/img2.png"]


def test_save_edit_draft(tmp_path: Path):
    path = tmp_path / "draft.json"
    cache = DraftCache(path=path)
    draft = _sample_draft(draft_type="edit", test_id="abc123")
    cache.save(draft)

    loaded = cache.load()
    assert loaded is not None
    assert loaded.draft_type == "edit"
    assert loaded.test_id == "abc123"


def test_exists_false_when_no_file(tmp_path: Path):
    cache = DraftCache(path=tmp_path / "draft.json")
    assert not cache.exists()


def test_exists_true_after_save(tmp_path: Path):
    path = tmp_path / "draft.json"
    cache = DraftCache(path=path)
    cache.save(_sample_draft())
    assert cache.exists()


def test_clear_removes_file(tmp_path: Path):
    path = tmp_path / "draft.json"
    cache = DraftCache(path=path)
    cache.save(_sample_draft())
    assert cache.exists()
    cache.clear()
    assert not cache.exists()


def test_clear_no_error_when_no_file(tmp_path: Path):
    cache = DraftCache(path=tmp_path / "draft.json")
    cache.clear()  # should not raise


def test_load_returns_none_when_no_file(tmp_path: Path):
    cache = DraftCache(path=tmp_path / "draft.json")
    assert cache.load() is None


def test_load_returns_none_on_corrupted_file(tmp_path: Path):
    path = tmp_path / "draft.json"
    path.write_text("NOT VALID JSON!!!", encoding="utf-8")
    cache = DraftCache(path=path)
    assert cache.load() is None
