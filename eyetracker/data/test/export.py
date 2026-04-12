"""ZIP export for a single test: image + JSON metadata."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from eyetracker.data.test.dao import TestDao, TestData


def export_test_zip(test: TestData, dao: TestDao, dest: Path) -> None:
    """Write *dest* as a ZIP containing the test image and ``test.json``.

    JSON structure::

        {
          "name": "Test name",
          "image": "./image.jpg",
          "aoi": [
            {
              "name": "Region",
              "color": "#00dc64",
              "first_fixation": false,
              "points": [{"x": 0.1, "y": 0.2}, ...]
            }
          ]
        }

    Image path inside the JSON is relative to the ZIP root (``./filename``).
    """
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        img_path = dao.get_image_path(test)
        if img_path.is_file():
            zf.write(img_path, test.image_filename)

        metadata = {
            "name": test.name,
            "image": f"./{test.image_filename}",
            "aoi": test.aoi,
        }
        zf.writestr("test.json", json.dumps(metadata, indent=2, ensure_ascii=False) + "\n")
