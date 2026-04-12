"""ROI hit detection and overlay utilities."""

from __future__ import annotations

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


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
    aoi: list[dict],
    fixations: list[dict],
) -> list[dict]:
    """Return per-AOI hit results."""
    rois = aoi
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


_FILL_ALPHA = 0.25
_LABEL_BG_ALPHA = 0.7
_PAD = 4
_FONT_SIZE = 42


def _get_pil_font() -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        # Try common system fonts that support Cyrillic
        for name in ("Arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf",
                     "/System/Library/Fonts/Helvetica.ttc",
                     "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
            try:
                return ImageFont.truetype(name, _FONT_SIZE)
            except OSError:
                continue
    except Exception:
        pass
    return ImageFont.load_default()


_PIL_FONT = _get_pil_font()


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

        # Name label at centroid (via Pillow for Unicode/Cyrillic support)
        name = roi.get("name", "")
        if name:
            cx = int(np.mean([p["x"] for p in points_n]) * w)
            cy = int(np.mean([p["y"] for p in points_n]) * h)
            pil_img = Image.fromarray(cv2.cvtColor(out, cv2.COLOR_BGR2RGB))
            draw = ImageDraw.Draw(pil_img)
            bbox = draw.textbbox((0, 0), name, font=_PIL_FONT)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            tx = max(_PAD, min(w - tw - _PAD, cx - tw // 2))
            ty = max(_PAD, min(h - th - _PAD, cy - th // 2))
            draw.rectangle(
                (tx - _PAD, ty - _PAD, tx + tw + _PAD, ty + th + _PAD),
                fill=(20, 20, 20, int(255 * _LABEL_BG_ALPHA)),
            )
            draw.text((tx, ty), name, font=_PIL_FONT, fill=(255, 255, 255))
            out = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

    return cv2.cvtColor(out, cv2.COLOR_BGR2RGB)
