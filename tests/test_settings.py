"""Tests for eyetracker.settings."""

import json
from pathlib import Path

from eyetracker.data.settings import Settings


def test_default_tracking_display_name_is_none(tmp_path: Path):
    s = Settings(path=tmp_path / "settings.json")
    assert s.tracking_display_name is None


def test_save_and_load(tmp_path: Path):
    path = tmp_path / "settings.json"
    s = Settings(path=path)
    s.tracking_display_name = "DELL U2720Q"

    s2 = Settings(path=path)
    assert s2.tracking_display_name == "DELL U2720Q"


def test_corrupted_file_fallback(tmp_path: Path):
    path = tmp_path / "settings.json"
    path.write_text("NOT VALID JSON!!!", encoding="utf-8")

    s = Settings(path=path)
    assert s.tracking_display_name is None


def test_set_none_removes_key(tmp_path: Path):
    path = tmp_path / "settings.json"
    s = Settings(path=path)
    s.tracking_display_name = "Monitor X"
    s.tracking_display_name = None

    data = json.loads(path.read_text(encoding="utf-8"))
    assert "tracking_display_name" not in data


def test_auth_token_default_none(tmp_path: Path):
    s = Settings(path=tmp_path / "settings.json")
    assert s.auth_token is None


def test_auth_token_save_and_load(tmp_path: Path):
    path = tmp_path / "settings.json"
    s = Settings(path=path)
    s.auth_token = "eyJ.payload.sig"

    s2 = Settings(path=path)
    assert s2.auth_token == "eyJ.payload.sig"


def test_auth_token_clear(tmp_path: Path):
    path = tmp_path / "settings.json"
    s = Settings(path=path)
    s.auth_token = "token"
    s.auth_token = None
    assert s.auth_token is None

    data = json.loads(path.read_text(encoding="utf-8"))
    assert "auth_token" not in data


def test_last_opened_test_id_default_none(tmp_path: Path):
    s = Settings(path=tmp_path / "settings.json")
    assert s.last_opened_test_id is None


def test_last_opened_test_id_save_and_load(tmp_path: Path):
    path = tmp_path / "settings.json"
    s = Settings(path=path)
    s.last_opened_test_id = "abc123"

    s2 = Settings(path=path)
    assert s2.last_opened_test_id == "abc123"
