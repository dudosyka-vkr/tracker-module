"""ROI hit detection and overlay utilities."""

from __future__ import annotations

import math

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


def fixation_aoi_sequence(aoi: list[dict], fixations: list[dict]) -> list[str | None]:
    """Map each fixation to the name of the first AOI it falls in, or None."""
    result = []
    for fx in fixations:
        cx, cy = fx["center"]["x"], fx["center"]["y"]
        label = next(
            (roi.get("name", "") for roi in aoi if point_in_polygon(cx, cy, roi.get("points", []))),
            None,
        )
        result.append(label)
    return result


def _count_revisits(sequence: list[str | None]) -> dict[str, int]:
    """Count per-AOI revisits from a fixation→AOI label sequence.

    A revisit is recorded each time gaze returns to an AOI after having left
    it (continuous runs in the same AOI count as a single visit).
    """
    revisits: dict[str, int] = {}
    seen: set[str] = set()
    prev: str | None = object()  # sentinel — never equal to any real label  # type: ignore[assignment]
    for label in sequence:
        if label == prev:
            continue  # same AOI as previous fixation, still the same visit
        prev = label
        if label is None:
            continue
        if label in seen:
            revisits[label] = revisits.get(label, 0) + 1
        else:
            seen.add(label)
            revisits[label] = 0
    return revisits


def compute_roi_metrics(
    aoi: list[dict],
    fixations: list[dict],
) -> list[dict]:
    """Return per-AOI hit results."""
    rois = aoi
    if not rois:
        return []

    first_fix = next((fx for fx in fixations if fx.get("is_first")), None)

    aoi_sequence = fixation_aoi_sequence(rois, fixations)
    revisits = _count_revisits(aoi_sequence)

    result = []
    for roi in rois:
        points = roi.get("points", [])
        first_required = roi.get("first_fixation", False)
        color = roi.get("color", "#00dc64")
        name = roi.get("name", "")

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

        aoi_first_fix = next(
            (
                fx.get("start_ms")
                for fx in fixations
                if point_in_polygon(fx["center"]["x"], fx["center"]["y"], points)
            ),
            None,
        )

        result.append({
            "name": name,
            "color": color,
            "hit": hit,
            "first_fixation_required": first_required,
            "aoi_first_fixation": aoi_first_fix,
            "revisits": revisits.get(name, 0),
        })
    return result


def compute_tge(aoi_sequence: list[str | None]) -> float | None:
    """Compute Transition Gaze Entropy (TGE) from a fixation→AOI label sequence.

    TGE = -∑_i p_i * ∑_j p(i→j) * log2(p(i→j))

    where p_i is the empirical dwell probability in AOI i (fraction of fixations
    that land in AOI i among all fixations in any named AOI), and p(i→j) is the
    probability of transitioning from AOI i to AOI j.

    Transitions are built from the run-length-compressed sequence so that
    consecutive fixations in the same zone count as a single visit, and gaps
    outside all AOIs (None) are bridged.

    Returns None if there are no named AOI visits, 0.0 if there is only one
    distinct AOI (no transitions possible).
    """
    # --- dwell probabilities from raw sequence ---
    dwell: dict[str, int] = {}
    for label in aoi_sequence:
        if label is not None:
            dwell[label] = dwell.get(label, 0) + 1

    if not dwell:
        return None

    total_dwell = sum(dwell.values())

    # --- transitions from run-length compressed sequence ---
    compressed: list[str | None] = []
    for label in aoi_sequence:
        if not compressed or compressed[-1] != label:
            compressed.append(label)

    transitions: dict[str, dict[str, int]] = {}
    last: str | None = None
    for label in compressed:
        if label is None:
            continue
        if last is not None:
            if last not in transitions:
                transitions[last] = {}
            transitions[last][label] = transitions[last].get(label, 0) + 1
        last = label

    if not transitions:
        return 0.0

    tge = 0.0
    for aoi_i, count_i in dwell.items():
        p_i = count_i / total_dwell
        row = transitions.get(aoi_i)
        if not row:
            continue
        total_from_i = sum(row.values())
        entropy_i = sum(
            -(c / total_from_i) * math.log2(c / total_from_i)
            for c in row.values()
        )
        tge += p_i * entropy_i

    return tge


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

        # Name label at centroid (via Pillow for Unicode/Cyrillic support)
        name = roi.get("name", "")
        if name:
            cx = int(np.mean([p["x"] for p in points_n]) * w)
            cy = int(np.mean([p["y"] for p in points_n]) * h)
            
            # Calculate font size based on image dimensions
            base_font_size = max(10, min(w, h) // 25)
            
            pil_img = Image.fromarray(cv2.cvtColor(out, cv2.COLOR_BGR2RGB))
            draw = ImageDraw.Draw(pil_img)
            
            # Try to load a TrueType font, fallback to default if not available
            try:
                label_font = ImageFont.truetype("arial.ttf", base_font_size)
            except (IOError, OSError):
                try:
                    label_font = ImageFont.truetype("DejaVuSans.ttf", base_font_size)
                except (IOError, OSError):
                    label_font = ImageFont.load_default()
            
            bbox = draw.textbbox((0, 0), name, font=label_font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            tx = max(_PAD, min(w - tw - _PAD, cx - tw // 2))
            ty = max(_PAD, min(h - th - _PAD, cy - th // 2))
            draw.rectangle(
                (tx - _PAD, ty - _PAD, tx + tw + _PAD, ty + th + _PAD),
                fill=(20, 20, 20, int(255 * _LABEL_BG_ALPHA)),
            )
            draw.text((tx, ty), name, font=label_font, fill=(255, 255, 255))
            out = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

    return cv2.cvtColor(out, cv2.COLOR_BGR2RGB)
