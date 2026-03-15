"""Tests for report export."""

import json
import zipfile

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


def test_zip_contains_report_json(tmp_path):
    path = tmp_path / "report.zip"
    export_record_zip(_make_record(), path)

    with zipfile.ZipFile(path) as zf:
        assert "report.json" in zf.namelist()
        data = json.loads(zf.read("report.json"))
        assert data["id"] == "r1"
        assert len(data["items"]) == 2


def test_zip_contains_per_image_json(tmp_path):
    path = tmp_path / "report.zip"
    export_record_zip(_make_record(), path)

    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        assert "image_1.json" in names
        assert "image_2.json" in names

        img1 = json.loads(zf.read("image_1.json"))
        assert img1["gaze_groups"][0]["x"] == 0.5

        img2 = json.loads(zf.read("image_2.json"))
        assert img2["gaze_groups"][0]["x"] == 0.3


def test_zip_file_count(tmp_path):
    path = tmp_path / "report.zip"
    export_record_zip(_make_record(), path)

    with zipfile.ZipFile(path) as zf:
        # report.json + image_1.json + image_2.json
        assert len(zf.namelist()) == 3
