"""ZIP export for a single test: full-size images + JSON metadata."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from eyetracker.data.test.dao import TestDao, TestData


def export_test_zip(test: TestData, dao: TestDao, dest: Path) -> None:
    """Write *dest* as a ZIP containing all test images and ``test.json``.

    JSON structure::

        {
          "name": "Test name",
          "cover": "./cover.jpg",
          "images": [
            {
              "path": "./001.jpg",
              "regions": [
                {
                  "name": "Region",
                  "color": "#00dc64",
                  "first_fixation": false,
                  "points": [{"x": 0.1, "y": 0.2}, ...]
                }
              ]
            }
          ]
        }

    Image paths inside the JSON are relative to the ZIP root (``./filename``).
    """
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        cover_path = dao.get_cover_path(test)
        if cover_path.is_file():
            zf.write(cover_path, test.cover_filename)

        images = []
        for filename in test.image_filenames:
            img_path = dao.get_image_path(test, filename)
            if img_path.is_file():
                zf.write(img_path, filename)
            images.append({
                "path": f"./{filename}",
                "regions": test.image_regions.get(filename, []),
            })

        metadata = {
            "name": test.name,
            "cover": f"./{test.cover_filename}",
            "images": images,
        }
        zf.writestr("test.json", json.dumps(metadata, indent=2, ensure_ascii=False) + "\n")
