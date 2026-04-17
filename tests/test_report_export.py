"""Tests for report export."""

import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

from eyetracker.core.report_export import export_record_zip
from eyetracker.data.record import Record, RecordMetrics


def _make_record() -> Record:
    return Record(
        id="r1",
        test_id="t1",
        user_login="local",
        started_at="2025-01-01T00:00:00Z",
        finished_at="2025-01-01T00:00:10Z",
        duration_ms=10000,
        metrics=RecordMetrics(gaze_groups=[{"x": 0.5, "y": 0.5, "count": 10}]),
        created_at="2025-01-01T00:00:10Z",
    )


def _write_image(path: Path) -> None:
    img = np.full((100, 150, 3), 128, dtype=np.uint8)
    cv2.imwrite(str(path), img)


# ---------------------------------------------------------------------------
# Fallback mode (no TestDao)
# ---------------------------------------------------------------------------

def test_zip_contains_report_json(tmp_path):
    path = tmp_path / "report.zip"
    export_record_zip(_make_record(), path)

    with zipfile.ZipFile(path) as zf:
        assert "report.json" in zf.namelist()
        data = json.loads(zf.read("report.json"))
        assert data["id"] == "r1"


def test_zip_fallback_flat_metrics_json(tmp_path):
    path = tmp_path / "report.zip"
    export_record_zip(_make_record(), path)

    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        assert "image/metrics.json" in names

        data = json.loads(zf.read("image/metrics.json"))
        assert data["gaze_groups"][0]["x"] == 0.5


def test_zip_fallback_no_image_files(tmp_path):
    path = tmp_path / "report.zip"
    export_record_zip(_make_record(), path)

    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        assert not any("original" in n for n in names)
        assert not any("heatmap" in n for n in names)


# ---------------------------------------------------------------------------
# Full mode (with TestDao + real images)
# ---------------------------------------------------------------------------

def _make_dao_and_data(tmp_path: Path):
    """Return (test_dao_mock, test_data_mock) backed by a real image file."""
    img = tmp_path / "image.png"
    _write_image(img)

    test_data = MagicMock()
    test_data.aoi = []
    test_dao = MagicMock()
    test_dao.get_image_path.return_value = img
    return test_dao, test_data


def test_zip_full_folder_structure(tmp_path):
    path = tmp_path / "report.zip"
    test_dao, test_data = _make_dao_and_data(tmp_path)
    export_record_zip(_make_record(), path, test_dao, test_data)

    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        assert "image/original.png" in names
        assert "image/heatmap.png" in names
        assert "image/metrics.json" in names


def test_zip_full_metrics_json_content(tmp_path):
    path = tmp_path / "report.zip"
    test_dao, test_data = _make_dao_and_data(tmp_path)
    export_record_zip(_make_record(), path, test_dao, test_data)

    with zipfile.ZipFile(path) as zf:
        data = json.loads(zf.read("image/metrics.json"))
        assert data["gaze_groups"][0]["x"] == pytest.approx(0.5)


def test_zip_full_heatmap_is_valid_image(tmp_path):
    path = tmp_path / "report.zip"
    test_dao, test_data = _make_dao_and_data(tmp_path)
    export_record_zip(_make_record(), path, test_dao, test_data)

    with zipfile.ZipFile(path) as zf:
        buf = zf.read("image/heatmap.png")
    arr = np.frombuffer(buf, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    assert img is not None
    assert img.shape == (100, 150, 3)


def test_zip_missing_image_file_falls_back(tmp_path):
    """If the image file doesn't exist, only metrics.json is written."""
    path = tmp_path / "report.zip"
    test_dao = MagicMock()
    test_data = MagicMock()
    test_dao.get_image_path.return_value = tmp_path / "nonexistent.png"

    export_record_zip(_make_record(), path, test_dao, test_data)

    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        assert "image/metrics.json" in names
        assert not any("original" in n for n in names)
