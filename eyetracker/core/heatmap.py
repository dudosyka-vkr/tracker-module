"""Gaze heatmap renderer.

Generates a heatmap image by overlaying Gaussian blobs (one per gaze group)
on top of the original stimulus image using the JET colormap.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def generate_heatmap(
    image_path: Path | str,
    gaze_groups: list[dict],
    *,
    sigma_fraction: float = 0.05,
    alpha: float = 0.6,
) -> np.ndarray:
    """Overlay a gaze heatmap on *image_path* and return the result as RGB.

    Args:
        image_path: Path to the source (stimulus) image.
        gaze_groups: List of ``{"x": float, "y": float, "count": int}`` dicts.
                     ``x`` and ``y`` are normalised to ``[0, 1]``.
        sigma_fraction: Gaussian blob radius expressed as a fraction of
                        ``max(image_width, image_height)``.  Larger values
                        produce bigger, softer blobs.
        alpha: Peak opacity of the heatmap layer (0 = invisible, 1 = opaque).
               Low-density pixels are automatically more transparent.

    Returns:
        RGB ``uint8`` numpy array of shape ``(H, W, 3)`` with the heatmap
        blended over the original image.

    Raises:
        FileNotFoundError: If *image_path* cannot be read by OpenCV.
    """
    img_bgr = cv2.imread(str(image_path))
    if img_bgr is None:
        raise FileNotFoundError(f"Cannot load image: {image_path}")
    h, w = img_bgr.shape[:2]

    density = _build_density(gaze_groups, w, h, sigma_fraction)

    if density.max() == 0:
        return cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

    density /= density.max()

    heatmap_bgr = cv2.applyColorMap(
        (density * 255).astype(np.uint8), cv2.COLORMAP_JET
    )

    blend = (density * alpha)[..., np.newaxis]
    result = img_bgr.astype(np.float32) * (1.0 - blend) + heatmap_bgr.astype(np.float32) * blend
    return cv2.cvtColor(np.clip(result, 0, 255).astype(np.uint8), cv2.COLOR_BGR2RGB)


def save_heatmap(
    image_path: Path | str,
    gaze_groups: list[dict],
    output_path: Path | str,
    *,
    sigma_fraction: float = 0.05,
    alpha: float = 0.6,
) -> None:
    """Generate a heatmap and write it to *output_path* (PNG/JPEG/…)."""
    rgb = generate_heatmap(
        image_path, gaze_groups, sigma_fraction=sigma_fraction, alpha=alpha
    )
    cv2.imwrite(str(output_path), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_density(
    gaze_groups: list[dict],
    w: int,
    h: int,
    sigma_fraction: float,
) -> np.ndarray:
    """Return a float32 density map of shape (H, W)."""
    density = np.zeros((h, w), dtype=np.float32)
    sigma = sigma_fraction * max(w, h)
    for group in gaze_groups:
        cx = float(group["x"]) * w
        cy = float(group["y"]) * h
        weight = float(group.get("count", 1))
        _add_gaussian(density, cx, cy, sigma, weight)
    return density


def _add_gaussian(
    density: np.ndarray,
    cx: float,
    cy: float,
    sigma: float,
    weight: float,
) -> None:
    """Accumulate a weighted 2-D Gaussian blob into *density* in-place."""
    h, w = density.shape
    radius = int(3 * sigma) + 1
    x0, x1 = max(0, int(cx) - radius), min(w, int(cx) + radius + 1)
    y0, y1 = max(0, int(cy) - radius), min(h, int(cy) + radius + 1)
    if x0 >= x1 or y0 >= y1:
        return
    xs = np.arange(x0, x1, dtype=np.float32) - cx
    ys = np.arange(y0, y1, dtype=np.float32) - cy
    xg, yg = np.meshgrid(xs, ys)
    density[y0:y1, x0:x1] += np.exp(-(xg ** 2 + yg ** 2) / (2.0 * sigma ** 2)) * weight
