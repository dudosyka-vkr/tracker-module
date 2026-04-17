"""AOI transition sequence map renderer.

Draws numbered arrows between AOI centroids in the order the gaze visited
them, overlaid on the stimulus image.  Self-transitions (returning to the
same AOI after leaving) are shown as a small loop arc above the centroid.
"""

from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from eyetracker.core.roi import overlay_rois


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_aoi_sequence_map(
    image_path: Path | str,
    aoi: list[dict],
    aoi_sequence: list[str | None],
) -> np.ndarray:
    """Render AOI transition arrows on *image_path* and return RGB.

    Args:
        image_path: Path to the stimulus image used as background.
        aoi: List of AOI dicts with ``"name"``, ``"color"``, and ``"points"``
             (normalized ``{x, y}`` dicts).
        aoi_sequence: Per-fixation AOI label sequence as stored in
                      ``RecordMetrics.aoi_sequence`` (``None`` = outside all AOIs).

    Returns:
        RGB ``uint8`` numpy array with AOI polygons and numbered transition
        arrows rendered on top of the image.

    Raises:
        FileNotFoundError: If *image_path* cannot be read by OpenCV.
    """
    img_bgr = cv2.imread(str(image_path))
    if img_bgr is None:
        raise FileNotFoundError(f"Cannot load image: {image_path}")
    h, w = img_bgr.shape[:2]

    # Draw AOI polygons first
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    rgb = overlay_rois(rgb, aoi)
    out = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

    # Build per-name centroid and color maps
    centroids: dict[str, tuple[int, int]] = {}
    aoi_colors: dict[str, tuple[int, int, int]] = {}
    for roi in aoi:
        name = roi.get("name", "")
        centroids[name] = _centroid(roi, w, h)
        aoi_colors[name] = _hex_to_bgr(roi.get("color", "#00dc64"))

    # Scale all drawing sizes relative to the image's shorter dimension.
    # Baseline: constants were tuned at 1000 px short side.
    scale = min(w, h) / 1000.0
    params = _DrawParams(scale, min(w, h))

    # Extract ordered transitions from the sequence
    transitions = _build_transitions(aoi_sequence)

    # Draw arrows + labels
    _draw_transitions(out, transitions, centroids, params)

    # Draw centroid anchor dots on top of arrows
    dot_r = params.centroid_r
    for name, (cx, cy) in centroids.items():
        color = aoi_colors.get(name, (200, 200, 200))
        cv2.circle(out, (cx, cy), dot_r + 2, (20, 20, 20), -1, cv2.LINE_AA)
        cv2.circle(out, (cx, cy), dot_r, color, -1, cv2.LINE_AA)

    return cv2.cvtColor(out, cv2.COLOR_BGR2RGB)


# ---------------------------------------------------------------------------
# Transition extraction
# ---------------------------------------------------------------------------


def _build_transitions(aoi_sequence: list[str | None]) -> list[tuple[str, str]]:
    """Return ordered list of (src, dst) AOI name pairs from the sequence.

    The sequence is first run-length compressed (consecutive same labels
    collapsed).  Transitions are then built between consecutive non-null
    entries, preserving self-transitions that occur when gaze returns to
    the same AOI after a period outside all AOIs.
    """
    # Run-length compress
    compressed: list[str | None] = []
    for label in aoi_sequence:
        if not compressed or compressed[-1] != label:
            compressed.append(label)

    # Walk compressed sequence; connect consecutive non-null entries
    transitions: list[tuple[str, str]] = []
    last: str | None = None
    for label in compressed:
        if label is None:
            continue
        if last is not None:
            transitions.append((last, label))
        last = label

    return transitions


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------

_ARROW_COLOR = (0, 200, 255)   # BGR cyan-yellow
_LABEL_BG    = (20, 20, 20)
_LABEL_FG    = (255, 255, 255)
_HEAD_ANGLE  = math.pi / 5    # arrowhead half-angle (36°)

# Font cache keyed by integer pixel size
_font_cache: dict[int, ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}


def _get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if size in _font_cache:
        return _font_cache[size]
    font = None
    for name in (
        "Arial Bold.ttf", "ArialBD.ttf", "Arial.ttf",
        "DejaVuSans-Bold.ttf", "DejaVuSans.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        try:
            font = ImageFont.truetype(name, size)
            break
        except OSError:
            pass
    if font is None:
        font = ImageFont.load_default(size)
    _font_cache[size] = font
    return font


class _DrawParams:
    """All drawing sizes derived from image scale (baseline: 1000 px short side)."""

    def __init__(self, scale: float, minWH: int) -> None:
        self.centroid_offset = int(30 * scale)
        self.curve_bend_base = int(100 * scale)
        self.curve_bend_step = int(80 * scale)
        self.arrow_thickness = max(1, int(6 * scale))
        self.head_len        = max(8, int(44 * scale))
        self.font_size       = max(10, int(minWH // 25))
        self.label_pad       = max(8, int(24 * scale))
        self.label_border    = max(2, int(3 * scale))
        self.centroid_r      = max(4, int(7 * scale))


def _draw_transitions(
    out: np.ndarray,
    transitions: list[tuple[str, str]],
    centroids: dict[str, tuple[int, int]],
    p: _DrawParams,
) -> None:
    pair_count: dict[tuple[str, str], int] = {}

    for i, (src, dst) in enumerate(transitions):
        if src not in centroids or dst not in centroids:
            continue

        label = str(i + 1)

        if src == dst:
            mx, my = _draw_self_loop(out, centroids[src], p)
        else:
            count = pair_count.get((src, dst), 0) + 1
            pair_count[(src, dst)] = count
            bend = p.curve_bend_base + (count - 1) * p.curve_bend_step
            mx, my = _draw_curved_arrow(out, centroids[src], centroids[dst], bend, p)

        _draw_label(out, label, mx, my, p)


def _bezier_pts(ps: tuple, cp: tuple, pe: tuple, steps: int = 40) -> list[tuple[int, int]]:
    result = []
    for k in range(steps + 1):
        t = k / steps
        x = int((1 - t) ** 2 * ps[0] + 2 * (1 - t) * t * cp[0] + t ** 2 * pe[0])
        y = int((1 - t) ** 2 * ps[1] + 2 * (1 - t) * t * cp[1] + t ** 2 * pe[1])
        result.append((x, y))
    return result


def _draw_curved_arrow(
    out: np.ndarray,
    p1: tuple[int, int],
    p2: tuple[int, int],
    bend: float,
    p: _DrawParams,
) -> tuple[int, int]:
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    dist = math.hypot(dx, dy)
    if dist < 1:
        return p1

    ux, uy = dx / dist, dy / dist
    px, py = -uy, ux

    ps = (int(p1[0] + ux * p.centroid_offset), int(p1[1] + uy * p.centroid_offset))
    pe = (int(p2[0] - ux * p.centroid_offset), int(p2[1] - uy * p.centroid_offset))

    mid_x = (ps[0] + pe[0]) / 2 + px * bend
    mid_y = (ps[1] + pe[1]) / 2 + py * bend
    cp = (int(mid_x), int(mid_y))

    pts = _bezier_pts(ps, cp, pe)
    arr = np.array(pts, dtype=np.int32).reshape(-1, 1, 2)
    cv2.polylines(out, [arr], False, _ARROW_COLOR, p.arrow_thickness, cv2.LINE_AA)

    tx = pe[0] - cp[0]
    ty = pe[1] - cp[1]
    tlen = math.hypot(tx, ty)
    if tlen > 0:
        tx, ty = tx / tlen, ty / tlen
        a = (int(pe[0] - p.head_len * (tx * math.cos(_HEAD_ANGLE) - ty * math.sin(_HEAD_ANGLE))),
             int(pe[1] - p.head_len * (ty * math.cos(_HEAD_ANGLE) + tx * math.sin(_HEAD_ANGLE))))
        b = (int(pe[0] - p.head_len * (tx * math.cos(_HEAD_ANGLE) + ty * math.sin(_HEAD_ANGLE))),
             int(pe[1] - p.head_len * (ty * math.cos(_HEAD_ANGLE) - tx * math.sin(_HEAD_ANGLE))))
        cv2.fillPoly(out, [np.array([pe, a, b], dtype=np.int32)], _ARROW_COLOR)

    return pts[len(pts) // 2]


def _draw_self_loop(
    out: np.ndarray,
    center: tuple[int, int],
    p: _DrawParams,
) -> tuple[int, int]:
    cx, cy = center
    ax, ay = int(22 * p.arrow_thickness / 6), int(14 * p.arrow_thickness / 6)
    axes = (ax, ay)
    lcy = cy - int(28 * p.arrow_thickness / 6)

    cv2.ellipse(out, (cx, lcy), axes, 0, 30, 330, _ARROW_COLOR, p.arrow_thickness, cv2.LINE_AA)

    tip_rad = math.radians(330)
    dir_rad = math.radians(320)
    tip    = (cx + int(axes[0] * math.cos(tip_rad)), lcy + int(axes[1] * math.sin(tip_rad)))
    dir_pt = (cx + int(axes[0] * math.cos(dir_rad)), lcy + int(axes[1] * math.sin(dir_rad)))
    if tip != dir_pt:
        cv2.arrowedLine(out, dir_pt, tip, _ARROW_COLOR, p.arrow_thickness, cv2.LINE_AA, tipLength=0.8)

    return cx, lcy - axes[1] - int(8 * p.arrow_thickness / 6)


def _draw_label(
    out: np.ndarray,
    text: str,
    mx: int,
    my: int,
    p: _DrawParams,
) -> None:
    font = _get_font(p.font_size)
    pil_img = Image.fromarray(cv2.cvtColor(out, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_img)

    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    radius = p.font_size // 2 + p.label_pad

    draw.ellipse(
        (mx - radius, my - radius, mx + radius, my + radius),
        fill=_LABEL_BG,
        outline=(0, 200, 255),
        width=p.label_border,
    )
    draw.text(
        (mx - tw // 2 - bbox[0], my - th // 2 - bbox[1]),
        text,
        font=font,
        fill=_LABEL_FG,
    )

    out[:] = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _centroid(roi: dict, w: int, h: int) -> tuple[int, int]:
    points = roi.get("points", [])
    if not points:
        return w // 2, h // 2
    cx = int(sum(p["x"] for p in points) / len(points) * w)
    cy = int(sum(p["y"] for p in points) / len(points) * h)
    return cx, cy


def _hex_to_bgr(color_hex: str) -> tuple[int, int, int]:
    s = color_hex.lstrip("#")
    try:
        r, g, b = int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    except (ValueError, IndexError):
        r, g, b = 0, 220, 100
    return (b, g, r)
