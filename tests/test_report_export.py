"""Tests for report export."""

import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

from eyetracker.core.report_export import export_record_zip
from eyetracker.data.record import Record, RecordItem, RecordItemMetrics


def _make_record() -> Record:
    return Record(
        id="r1",
        test_id="t1",
        user_login="local",
        started_at="2025-01-01T00:00:00Z",
        finished_at="2025-01-01T00:00:10Z",
        duration_ms=10000,
        items=[
            RecordItem(
                image_filename="img1.png",
                image_index=0,
                metrics=RecordItemMetrics(gaze_groups=[{"x": 0.5, "y": 0.5, "count": 10}]),
            ),
            RecordItem(
                image_filename="img2.png",
                image_index=1,
                metrics=RecordItemMetrics(gaze_groups=[{"x": 0.3, "y": 0.7, "count": 5}]),
            ),
        ],
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
        assert len(data["items"]) == 2


def test_zip_fallback_flat_metrics_json(tmp_path):
    path = tmp_path / "report.zip"
    export_record_zip(_make_record(), path)

    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        assert "image_1/metrics.json" in names
        assert "image_2/metrics.json" in names

        data = json.loads(zf.read("image_1/metrics.json"))
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
    """Return (test_dao_mock, test_data_mock) backed by real image files."""
    img1 = tmp_path / "img1.png"
    img2 = tmp_path / "img2.png"
    _write_image(img1)
    _write_image(img2)

    test_data = MagicMock()
    test_dao = MagicMock()
    test_dao.get_image_path.side_effect = lambda td, fn: tmp_path / fn
    return test_dao, test_data


def test_zip_full_folder_structure(tmp_path):
    path = tmp_path / "report.zip"
    test_dao, test_data = _make_dao_and_data(tmp_path)
    export_record_zip(_make_record(), path, test_dao, test_data)

    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        assert "image_1/original.png" in names
        assert "image_1/heatmap.png" in names
        assert "image_1/metrics.json" in names
        assert "image_2/original.png" in names
        assert "image_2/heatmap.png" in names
        assert "image_2/metrics.json" in names


def test_zip_full_metrics_json_content(tmp_path):
    path = tmp_path / "report.zip"
    test_dao, test_data = _make_dao_and_data(tmp_path)
    export_record_zip(_make_record(), path, test_dao, test_data)

    with zipfile.ZipFile(path) as zf:
        data = json.loads(zf.read("image_2/metrics.json"))
        assert data["gaze_groups"][0]["x"] == pytest.approx(0.3)


def test_zip_full_heatmap_is_valid_image(tmp_path):
    path = tmp_path / "report.zip"
    test_dao, test_data = _make_dao_and_data(tmp_path)
    export_record_zip(_make_record(), path, test_dao, test_data)

    with zipfile.ZipFile(path) as zf:
        buf = zf.read("image_1/heatmap.png")
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
        assert "image_1/metrics.json" in names
        assert not any("original" in n for n in names)
