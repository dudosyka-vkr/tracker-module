"""Gaze points map renderer.

Draws each gaze group as a dot colored by inter-sample velocity
(blue = slow, red = fast) overlaid on the stimulus image.
Also provides saccade vector visualisation.
"""

from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np


def generate_gaze_points_map(
    image_path: Path | str,
    gaze_groups: list[dict],
    *,
    radius: int = 4,
) -> np.ndarray:
    """Overlay raw gaze points on *image_path* and return the result as RGB.

    Each dot is colored by velocity relative to the previous point:
    blue = slow (or first point), red = fast.

    Args:
        image_path: Path to the source (stimulus) image.
        gaze_groups: List of ``{"x": float, "y": float, "count": int}`` dicts
                     with optional ``"time_ms": int``.  ``x`` and ``y`` are
                     normalised to ``[0, 1]``.
        radius: Radius of each dot in pixels.

    Returns:
        RGB ``uint8`` numpy array of shape ``(H, W, 3)``.

    Raises:
        FileNotFoundError: If *image_path* cannot be read by OpenCV.
    """
    img_bgr = cv2.imread(str(image_path))
    if img_bgr is None:
        raise FileNotFoundError(f"Cannot load image: {image_path}")
    h, w = img_bgr.shape[:2]
    out = img_bgr.copy()

    velocities = _compute_velocities(gaze_groups)
    max_v = max(velocities) if velocities else 1.0

    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.3
    font_thickness = 1

    for i, group in enumerate(gaze_groups):
        cx = int(float(group["x"]) * w)
        cy = int(float(group["y"]) * h)
        color = _velocity_color(velocities[i], max_v)
        cv2.circle(out, (cx, cy), radius, color, -1, cv2.LINE_AA)

        label = str(i + 1)
        (tw, th), _ = cv2.getTextSize(label, font, font_scale, font_thickness)
        cv2.putText(out, label, (cx - tw // 2, cy - radius - 2),
                    font, font_scale, (255, 255, 255), font_thickness, cv2.LINE_AA)

    return cv2.cvtColor(out, cv2.COLOR_BGR2RGB)


def generate_saccade_map(
    image_path: Path | str,
    saccades: list[dict],
    *,
    dot_radius: int = 3,
    dash_len: int = 10,
    gap_len: int = 6,
) -> np.ndarray:
    """Overlay pre-computed saccade vectors on *image_path* and return the result as RGB.

    Each saccade is drawn as a dashed vector following its gaze points
    point-by-point, with an arrowhead from start to end and a duration label
    at the midpoint of the vector.

    Args:
        image_path: Path to the source (stimulus) image.
        saccades: List of saccade dicts as stored in ``RecordItemMetrics.saccades``.
                  Each dict has ``"duration_ms"`` (float | None) and ``"points"``
                  (list of ``{"x", "y", "time_ms", "velocity"}``).
        dot_radius: Radius of each punctir dot in pixels.
        dash_len: Length of each drawn dash segment in pixels.
        gap_len: Length of the gap between dash segments in pixels.

    Returns:
        RGB ``uint8`` numpy array of shape ``(H, W, 3)``.

    Raises:
        FileNotFoundError: If *image_path* cannot be read by OpenCV.
    """
    img_bgr = cv2.imread(str(image_path))
    if img_bgr is None:
        raise FileNotFoundError(f"Cannot load image: {image_path}")
    h, w = img_bgr.shape[:2]
    out = img_bgr.copy()

    vector_color = (0, 200, 255)
    dot_color    = (0, 220, 255)
    label_bg     = (30, 30, 30)
    label_fg     = (255, 255, 255)
    font         = cv2.FONT_HERSHEY_SIMPLEX
    font_scale   = 0.4
    font_thick   = 1

    for saccade in saccades:
        points = saccade.get("points", [])
        if len(points) < 2:
            continue

        pts = [
            (int(float(p["x"]) * w), int(float(p["y"]) * h))
            for p in points
        ]

        # Draw dashed segments between consecutive gaze points
        for k in range(len(pts) - 1):
            _draw_dashed_segment(out, pts[k], pts[k + 1], dot_color, dot_radius, dash_len, gap_len)

        # Arrowhead from start → end to show direction
        if pts[0] != pts[-1]:
            cv2.arrowedLine(out, pts[0], pts[-1], vector_color, 2, cv2.LINE_AA, tipLength=0.07)

        # Start and end marker dots
        cv2.circle(out, pts[0],  dot_radius + 1, vector_color, -1, cv2.LINE_AA)
        cv2.circle(out, pts[-1], dot_radius + 1, vector_color, -1, cv2.LINE_AA)

        # Duration label: midpoint of the straight start→end vector, raised above it
        mx = (pts[0][0] + pts[-1][0]) // 2
        my = (pts[0][1] + pts[-1][1]) // 2
        duration_ms = saccade.get("duration_ms")
        label = f"{duration_ms:.0f} ms" if duration_ms is not None else f"{len(points)} pts"

        (tw, th), baseline = cv2.getTextSize(label, font, font_scale, font_thick)
        pad = 3
        offset_y = th + pad + 6
        tx = mx - tw // 2
        ty = my - offset_y
        cv2.rectangle(
            out,
            (tx - pad, ty - th - pad),
            (tx + tw + pad, ty + baseline + pad),
            label_bg,
            -1,
        )
        cv2.putText(out, label, (tx, ty), font, font_scale, label_fg, font_thick, cv2.LINE_AA)

    return cv2.cvtColor(out, cv2.COLOR_BGR2RGB)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compute_velocities(gaze_groups: list[dict]) -> list[float]:
    """Return per-point velocity in normalised units/ms (0.0 for first point)."""
    result: list[float] = []
    for i, group in enumerate(gaze_groups):
        if i == 0:
            result.append(0.0)
            continue
        prev = gaze_groups[i - 1]
        dx = float(group["x"]) - float(prev["x"])
        dy = float(group["y"]) - float(prev["y"])
        dist = math.hypot(dx, dy)

        t_cur = group.get("time_ms")
        t_prev = prev.get("time_ms")
        if t_cur is not None and t_prev is not None:
            dt = t_cur - t_prev
            velocity = dist / dt if dt > 0 else 0.0
        else:
            velocity = dist  # fallback: distance only, no time info
        result.append(velocity)
    return result


def _draw_dashed_segment(
    img: np.ndarray,
    pt1: tuple[int, int],
    pt2: tuple[int, int],
    color: tuple[int, int, int],
    dot_radius: int,
    dash_len: int,
    gap_len: int,
) -> None:
    """Draw a dashed line between *pt1* and *pt2* using filled circles as dots."""
    x1, y1 = pt1
    x2, y2 = pt2
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    if length < 1:
        cv2.circle(img, pt1, dot_radius, color, -1, cv2.LINE_AA)
        return

    ux, uy = dx / length, dy / length
    step = dash_len + gap_len
    pos = 0.0
    while pos < length:
        seg_end = min(pos + dash_len, length)
        d = pos
        while d <= seg_end:
            cx = int(x1 + ux * d)
            cy = int(y1 + uy * d)
            cv2.circle(img, (cx, cy), dot_radius, color, -1, cv2.LINE_AA)
            d += max(dot_radius * 2, 1)
        pos += step


def _velocity_color(v: float, max_v: float) -> tuple[int, int, int]:
    """Return a BGR color interpolated blue→green→red by normalised velocity."""
    t = v / max_v if max_v > 0 else 0.0
    t = max(0.0, min(1.0, t))
    if t < 0.5:
        s = t * 2.0
        b = int(255 * (1.0 - s))
        g = int(255 * s)
        r = 0
    else:
        s = (t - 0.5) * 2.0
        b = 0
        g = int(255 * (1.0 - s))
        r = int(255 * s)
    return (b, g, r)
