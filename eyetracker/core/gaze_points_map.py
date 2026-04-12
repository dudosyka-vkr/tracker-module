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
from PIL import Image, ImageDraw

from eyetracker.core.aoi_sequence_map import _get_font


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

    Each saccade is drawn as a dashed path with a straight filled-triangle arrow
    from start to end and a PIL circle-badge label at the midpoint.

    Args:
        image_path: Path to the source (stimulus) image.
        saccades: List of saccade dicts as stored in ``RecordMetrics.saccades``.
                  Each dict has ``"duration_ms"`` (float | None) and ``"points"``
                  (list of ``{"x", "y", "time_ms", "velocity"}``).
        dot_radius: Unused — kept for API compatibility (value is now scale-derived).
        dash_len: Unused — kept for API compatibility (value is now scale-derived).
        gap_len: Unused — kept for API compatibility (value is now scale-derived).

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

    # All sizes scale with the shorter image dimension (baseline: 1000 px)
    scale        = min(w, h) / 1000.0
    s_dot_radius = max(2, int(4 * scale))
    s_dash_len   = max(6, int(12 * scale))
    s_gap_len    = max(4, int(7 * scale))
    s_thickness  = max(1, int(6 * scale))
    s_head_len   = max(8, int(44 * scale))
    s_font_size  = max(10, int(56 * scale))
    s_label_pad  = max(8, int(24 * scale))
    s_label_bord = max(2, int(3 * scale))
    head_angle   = math.pi / 5   # 36°

    vector_color = (0, 200, 255)
    dot_color    = (0, 220, 255)
    font         = _get_font(s_font_size)

    for saccade in saccades:
        points = saccade.get("points", [])
        if len(points) < 2:
            continue

        pts = [
            (int(float(p["x"]) * w), int(float(p["y"]) * h))
            for p in points
        ]

        # Straight filled-triangle arrow from start → end
        p_start, p_end = pts[0], pts[-1]
        if p_start != p_end:
            cv2.line(out, p_start, p_end, vector_color, s_thickness, cv2.LINE_AA)
            dx = p_end[0] - p_start[0]
            dy = p_end[1] - p_start[1]
            dist = math.hypot(dx, dy)
            tx, ty = dx / dist, dy / dist
            a = (int(p_end[0] - s_head_len * (tx * math.cos(head_angle) - ty * math.sin(head_angle))),
                 int(p_end[1] - s_head_len * (ty * math.cos(head_angle) + tx * math.sin(head_angle))))
            b = (int(p_end[0] - s_head_len * (tx * math.cos(head_angle) + ty * math.sin(head_angle))),
                 int(p_end[1] - s_head_len * (ty * math.cos(head_angle) - tx * math.sin(head_angle))))
            cv2.fillPoly(out, [np.array([p_end, a, b], dtype=np.int32)], vector_color)

        # Start / end marker dots
        cv2.circle(out, p_start, s_dot_radius + 2, vector_color, -1, cv2.LINE_AA)
        cv2.circle(out, p_end,   s_dot_radius + 2, vector_color, -1, cv2.LINE_AA)

        # PIL circle-badge label at midpoint
        mx = (p_start[0] + p_end[0]) // 2
        my = (p_start[1] + p_end[1]) // 2
        duration_ms = saccade.get("duration_ms")
        label = f"{duration_ms:.0f}ms" if duration_ms is not None else f"{len(points)}pts"
        _draw_saccade_label(out, label, mx, my, font, s_label_pad, s_label_bord)

    return cv2.cvtColor(out, cv2.COLOR_BGR2RGB)


def _draw_saccade_label(
    out: np.ndarray,
    text: str,
    mx: int,
    my: int,
    font,
    pad: int,
    border: int,
) -> None:
    """Draw a PIL rounded-rectangle badge with *text* centred on *(mx, my)*."""
    pil_img = Image.fromarray(cv2.cvtColor(out, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_img)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    half_w = tw // 2 + pad
    half_h = th // 2 + pad
    corner_r = half_h  # fully rounded on short axis
    draw.rounded_rectangle(
        (mx - half_w, my - half_h, mx + half_w, my + half_h),
        radius=corner_r,
        fill=(20, 20, 20),
        outline=(0, 200, 255),
        width=border,
    )
    draw.text(
        (mx - tw // 2 - bbox[0], my - th // 2 - bbox[1]),
        text,
        font=font,
        fill=(255, 255, 255),
    )
    out[:] = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)


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
