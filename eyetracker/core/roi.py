"""ROI hit detection and overlay utilities."""

from __future__ import annotations

import cv2
import numpy as np


def point_in_polygon(px: float, py: float, points: list[dict]) -> bool:
    """Ray-casting point-in-polygon test. points are {x, y} normalized dicts."""
    n = len(points)
    if n < 3:
        return False
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = points[i]["x"], points[i]["y"]
        xj, yj = points[j]["x"], points[j]["y"]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def compute_roi_metrics(
    regions: dict[str, list[dict]],
    filename: str,
    fixations: list[dict],
) -> list[dict]:
    """Return per-ROI hit results for one image."""
    rois = regions.get(filename, [])
    if not rois:
        return []

    first_fix = next((fx for fx in fixations if fx.get("is_first")), None)

    result = []
    for roi in rois:
        points = roi.get("points", [])
        first_required = roi.get("first_fixation", False)
        color = roi.get("color", "#00dc64")

        if first_required:
            hit = (
                first_fix is not None
                and point_in_polygon(
                    first_fix["center"]["x"],
                    first_fix["center"]["y"],
                    points,
                )
            )
        else:
            hit = any(
                point_in_polygon(fx["center"]["x"], fx["center"]["y"], points)
                for fx in fixations
            )

        result.append({
            "name": roi.get("name", ""),
            "color": color,
            "hit": hit,
            "first_fixation_required": first_required,
        })
    return result


_FONT = cv2.FONT_HERSHEY_SIMPLEX
_FONT_SCALE = 0.55
_FONT_THICKNESS = 1
_FILL_ALPHA = 0.25
_LABEL_BG_ALPHA = 0.7
_PAD = 4


def overlay_rois(rgb: np.ndarray, rois: list[dict]) -> np.ndarray:
    """Draw ROI polygons over an RGB image and return the result as RGB.

    Each ROI is rendered as a semi-transparent filled polygon with a solid
    outline and a name label at the polygon centroid.

    Args:
        rgb:  RGB uint8 array of shape (H, W, 3).
        rois: List of ROI dicts with ``"points"`` (normalized {x,y}),
              ``"color"`` (hex string) and ``"name"`` keys.

    Returns:
        New RGB array with ROIs drawn on top.
    """
    if not rois:
        return rgb

    h, w = rgb.shape[:2]
    out = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

    for roi in rois:
        points_n = roi.get("points", [])
        if len(points_n) < 3:
            continue

        color_hex = roi.get("color", "#00dc64").lstrip("#")
        try:
            r_c = int(color_hex[0:2], 16)
            g_c = int(color_hex[2:4], 16)
            b_c = int(color_hex[4:6], 16)
        except (ValueError, IndexError):
            r_c, g_c, b_c = 0, 220, 100
        bgr = (b_c, g_c, r_c)

        pts = np.array(
            [[int(p["x"] * w), int(p["y"] * h)] for p in points_n],
            dtype=np.int32,
        ).reshape((-1, 1, 2))

        # Semi-transparent fill
        overlay = out.copy()
        cv2.fillPoly(overlay, [pts], bgr)
        cv2.addWeighted(overlay, _FILL_ALPHA, out, 1.0 - _FILL_ALPHA, 0, out)

        # Solid outline
        cv2.polylines(out, [pts], True, bgr, 2, cv2.LINE_AA)

        # Name label at centroid
        name = roi.get("name", "")
        if name:
            cx = int(np.mean([p["x"] for p in points_n]) * w)
            cy = int(np.mean([p["y"] for p in points_n]) * h)
            (tw, th), baseline = cv2.getTextSize(name, _FONT, _FONT_SCALE, _FONT_THICKNESS)
            tx = max(_PAD, min(w - tw - _PAD, cx - tw // 2))
            ty = max(th + _PAD, min(h - baseline - _PAD, cy))
            rx0 = max(0, tx - _PAD)
            ry0 = max(0, ty - th - _PAD)
            rx1 = min(w, tx + tw + _PAD)
            ry1 = min(h, ty + baseline + _PAD)
            bg_overlay = out.copy()
            cv2.rectangle(bg_overlay, (rx0, ry0), (rx1, ry1), (20, 20, 20), -1)
            cv2.addWeighted(bg_overlay, _LABEL_BG_ALPHA, out, 1.0 - _LABEL_BG_ALPHA, 0, out)
            cv2.putText(
                out, name, (tx, ty),
                _FONT, _FONT_SCALE, (255, 255, 255), _FONT_THICKNESS, cv2.LINE_AA,
            )

    return cv2.cvtColor(out, cv2.COLOR_BGR2RGB)
