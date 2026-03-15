"""Export record as a zip archive."""

from __future__ import annotations

import json
import zipfile
from dataclasses import asdict
from pathlib import Path

from eyetracker.data.record.service import Record


def export_record_zip(record: Record, save_path: Path) -> None:
    """Create a zip archive with report.json and per-image JSON files."""
    with zipfile.ZipFile(save_path, "w", zipfile.ZIP_DEFLATED) as zf:
        full_json = json.dumps(asdict(record), indent=2, ensure_ascii=False)
        zf.writestr("report.json", full_json)

        for item in record.items:
            idx = item.image_index + 1
            item_json = json.dumps(asdict(item.metrics), indent=2, ensure_ascii=False)
            zf.writestr(f"image_{idx}.json", item_json)
