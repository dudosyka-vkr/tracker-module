"""Export record as a zip archive."""

from __future__ import annotations

import json
import zipfile
from dataclasses import asdict
from pathlib import Path

import cv2

from eyetracker.core.heatmap import generate_heatmap
from eyetracker.data.record.service import Record
from eyetracker.data.test import TestDao, TestData


def export_record_zip(
    record: Record,
    save_path: Path,
    test_dao: TestDao | None = None,
    test_data: TestData | None = None,
) -> None:
    """Create a zip archive for *record*.

    Structure when image sources are available::

        report.json
        image_1/
            original.<ext>
            heatmap.png
            metrics.json
        image_2/
            ...

    Falls back to a flat ``image_N.json`` layout when *test_dao* / *test_data*
    are not provided or an image file cannot be found.
    """
    with zipfile.ZipFile(save_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("report.json", json.dumps(asdict(record), indent=2, ensure_ascii=False))

        for item in record.items:
            idx = item.image_index + 1
            folder = f"image_{idx}"
            metrics_json = json.dumps(asdict(item.metrics), indent=2, ensure_ascii=False)

            image_path: Path | None = None
            if test_dao is not None and test_data is not None:
                candidate = test_dao.get_image_path(test_data, item.image_filename)
                if candidate.exists():
                    image_path = candidate

            if image_path is None:
                # Fallback: flat json only (no image sources available)
                zf.writestr(f"{folder}/metrics.json", metrics_json)
                continue

            # Original image
            suffix = image_path.suffix or ".png"
            zf.write(image_path, f"{folder}/original{suffix}")

            # Heatmap image
            try:
                rgb = generate_heatmap(image_path, item.metrics.gaze_groups)
                bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
                ok, buf = cv2.imencode(".png", bgr)
                if ok:
                    zf.writestr(f"{folder}/heatmap.png", buf.tobytes())
            except Exception:
                pass

            # Metrics JSON
            zf.writestr(f"{folder}/metrics.json", metrics_json)
