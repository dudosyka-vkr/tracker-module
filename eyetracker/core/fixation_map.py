"""Fixation map renderer.

Renders a single fixation point (circle + emotion label) on top of a stimulus
image.  Fixation centre coordinates must be normalised to ``[0, 1]``.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def generate_all_fixations_map(
    image_path: Path | str,
    fixations: list[dict],
    *,
    circle_radius_fraction: float = 0.04,
) -> np.ndarray:
    """Render all fixation points on *image_path* at once and return RGB.

    Each circle has a dot inside.  A label ``#N emotion, Xms`` is drawn
    above/below each circle.

    Args:
        image_path: Path to the source (stimulus) image.
        fixations: List of fixation dicts with normalised ``center`` coords.
        circle_radius_fraction: Marker radius as a fraction of
                                 ``max(image_width, image_height)``.

    Returns:
        RGB ``uint8`` numpy array of shape ``(H, W, 3)``.

    Raises:
        FileNotFoundError: If *image_path* cannot be read.
    """
    img_bgr = cv2.imread(str(image_path))
    if img_bgr is None:
        raise FileNotFoundError(f"Cannot load image: {image_path}")
    h, w = img_bgr.shape[:2]

    out = img_bgr.copy()
    radius = max(8, int(circle_radius_fraction * max(w, h)))

    for i, fixation in enumerate(fixations):
        center = fixation.get("center", {})
        nx = float(center.get("x", 0.5))
        ny = float(center.get("y", 0.5))
        emotion = fixation.get("emotion") or "—"
        time_ms = fixation.get("time_ms")
        label = f'#{i + 1} {emotion}, {time_ms}ms'

        if nx > 1.0 or ny > 1.0:
            cx = max(0, min(int(nx), w - 1))
            cy = max(0, min(int(ny), h - 1))
        else:
            cx = int(nx * w)
            cy = int(ny * h)

        # Semi-transparent fill
        overlay = out.copy()
        cv2.circle(overlay, (cx, cy), radius, (0, 200, 255), -1)
        cv2.addWeighted(overlay, 0.35, out, 0.65, 0, out)

        # Ring
        cv2.circle(out, (cx, cy), radius, (0, 180, 255), 2, cv2.LINE_AA)

        # Number + time inside circle
        _draw_number(out, None, cx, cy)

        # Emotion label outside circle
        _draw_label(out, label, cx, cy, radius, w, h)

    return cv2.cvtColor(out, cv2.COLOR_BGR2RGB)


def generate_fixation_map(
    image_path: Path | str,
    fixation: dict,
    *,
    number: int | None = None,
    circle_radius_fraction: float = 0.04,
) -> np.ndarray:
    """Overlay a single fixation marker on *image_path* and return RGB.

    Args:
        image_path: Path to the source (stimulus) image.
        fixation: Dict with ``{"center": {"x": float, "y": float},
                  "emotion": str}``.  ``x`` and ``y`` are normalised to
                  ``[0, 1]``.
        circle_radius_fraction: Marker radius as a fraction of
                                 ``max(image_width, image_height)``.

    Returns:
        RGB ``uint8`` numpy array of shape ``(H, W, 3)``.

    Raises:
        FileNotFoundError: If *image_path* cannot be read.
    """
    img_bgr = cv2.imread(str(image_path))
    if img_bgr is None:
        raise FileNotFoundError(f"Cannot load image: {image_path}")
    h, w = img_bgr.shape[:2]

    center = fixation.get("center", {})
    nx = float(center.get("x", 0.5))
    ny = float(center.get("y", 0.5))
    emotion = fixation.get("emotion") or "—"

    # Coords > 1 are raw screen pixels (legacy records); <= 1 are normalised.
    if nx > 1.0 or ny > 1.0:
        cx = max(0, min(int(nx), w - 1))
        cy = max(0, min(int(ny), h - 1))
    else:
        cx = int(nx * w)
        cy = int(ny * h)
    radius = max(8, int(circle_radius_fraction * max(w, h)))

    out = img_bgr.copy()

    # Semi-transparent filled circle
    overlay = out.copy()
    cv2.circle(overlay, (cx, cy), radius, (0, 200, 255), -1)  # filled amber
    cv2.addWeighted(overlay, 0.35, out, 0.65, 0, out)

    # Solid ring on top
    cv2.circle(out, (cx, cy), radius, (0, 180, 255), 2, cv2.LINE_AA)

    # Number inside circle (or small dot if no number)
    if number is not None:
        _draw_number(out, number, cx, cy)
    else:
        cv2.circle(out, (cx, cy), 4, (255, 255, 255), -1, cv2.LINE_AA)

    # Emotion label
    _draw_label(out, emotion, cx, cy, radius, w, h)

    return cv2.cvtColor(out, cv2.COLOR_BGR2RGB)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_FONT = cv2.FONT_HERSHEY_SIMPLEX
_FONT_SCALE = 0.55
_FONT_THICKNESS = 1
_INNER_SCALE = 0.48   # smaller scale for text inside circles
_PAD = 6


def _draw_number(img: np.ndarray, number: int | str, cx: int, cy: int) -> None:
    """Draw text centred inside the fixation circle (single line)."""
    text = str(number or '.')
    (tw, th), _ = cv2.getTextSize(text, _FONT, _INNER_SCALE, _FONT_THICKNESS)
    tx = cx - tw // 2
    ty = cy + th // 2
    cv2.putText(img, text, (tx, ty), _FONT, _INNER_SCALE,
                (255, 255, 255), _FONT_THICKNESS, cv2.LINE_AA)


def _draw_label(
    img: np.ndarray,
    text: str,
    cx: int,
    cy: int,
    radius: int,
    img_w: int,
    img_h: int,
) -> None:
    """Draw a dark-background text label near the fixation circle."""
    (tw, th), baseline = cv2.getTextSize(text, _FONT, _FONT_SCALE, _FONT_THICKNESS)

    # Prefer label above the circle; fall back to below if too close to top.
    label_y = cy - radius - _PAD
    text_y = label_y - baseline
    if text_y - th - _PAD < 0:
        label_y = cy + radius + th + _PAD * 2
        text_y = label_y - baseline

    label_x = cx - tw // 2
    # Clamp so the label stays inside the image
    label_x = max(_PAD, min(img_w - tw - _PAD, label_x))

    # Background rect
    rx0, ry0 = label_x - _PAD, label_y - th - _PAD
    rx1, ry1 = label_x + tw + _PAD, label_y + baseline + _PAD
    rx0, ry0 = max(0, rx0), max(0, ry0)
    rx1, ry1 = min(img_w, rx1), min(img_h, ry1)

    # Semi-transparent dark background
    overlay = img.copy()
    cv2.rectangle(overlay, (rx0, ry0), (rx1, ry1), (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.7, img, 0.3, 0, img)

    cv2.putText(
        img, text, (label_x, text_y),
        _FONT, _FONT_SCALE, (255, 255, 255), _FONT_THICKNESS, cv2.LINE_AA,
    )
