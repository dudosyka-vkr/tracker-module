"""Utility classes and functions.

Provides Eye, DataWindow, KalmanFilter, and image processing helpers.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


class Eye:
    """Represents an eye patch detected in the video stream."""

    __slots__ = ("patch", "imagex", "imagey", "width", "height", "blink", "pupil")

    def __init__(
        self,
        patch: NDArray[np.uint8],
        imagex: int,
        imagey: int,
        width: int,
        height: int,
    ):
        self.patch = patch  # RGBA uint8 array of shape (height, width, 4)
        self.imagex = imagex
        self.imagey = imagey
        self.width = width
        self.height = height
        self.blink = False
        self.pupil: tuple[list[int], int] | None = None


class DataWindow:
    """Circular buffer that wraps data around a fixed window size.

    Operates like an array but keeps at most *window_size* elements.
    """

    def __init__(self, window_size: int, data: list | None = None):
        self.window_size = window_size
        self.index = 0
        if data:
            self.data = list(data[-window_size:])
        else:
            self.data: list = []

    @property
    def length(self) -> int:
        return len(self.data)

    def push(self, entry) -> "DataWindow":
        if len(self.data) < self.window_size:
            self.data.append(entry)
            return self
        self.data[self.index] = entry
        self.index = (self.index + 1) % self.window_size
        return self

    def get(self, ind: int):
        return self.data[self._true_index(ind)]

    def _true_index(self, ind: int) -> int:
        if len(self.data) < self.window_size:
            return ind
        return (ind + self.index) % self.window_size

    def add_all(self, data: list):
        for item in data:
            self.push(item)


# ---------------------------------------------------------------------------
# Image processing helpers
# ---------------------------------------------------------------------------

def grayscale(image_data: NDArray[np.uint8], width: int, height: int) -> NDArray[np.uint8]:
    """Convert RGBA pixel data to grayscale.

    Args:
        image_data: flat RGBA array of length width*height*4
        width: image width
        height: image height

    Returns:
        1-D uint8 array of length width*height
    """
    rgba = image_data.reshape(height, width, 4) if image_data.ndim == 1 else image_data
    # Standard luminance formula
    gray = (0.299 * rgba[..., 0] + 0.587 * rgba[..., 1] + 0.114 * rgba[..., 2]).astype(np.uint8)
    return gray.ravel()


def equalize_histogram(src: NDArray[np.uint8], step: int = 5, dst: NDArray | None = None) -> NDArray[np.uint8]:
    """Histogram equalization with step-based sampling.

    Args:
        src: 1-D grayscale uint8 array
        step: sampling step for histogram computation
        dst: optional destination array (same length as src)

    Returns:
        equalized uint8 array
    """
    length = len(src)
    if dst is None or len(dst) == 0:
        dst = np.empty(length, dtype=np.uint8)

    # Build histogram
    hist = np.zeros(256, dtype=np.int32)
    for i in range(0, length, step):
        hist[src[i]] += 1

    # Cumulative distribution
    total_samples = length // step
    if total_samples == 0:
        total_samples = 1
    cumsum = 0
    lut = np.zeros(256, dtype=np.uint8)
    for i in range(256):
        cumsum += hist[i]
        lut[i] = np.clip((cumsum * 255) // total_samples, 0, 255)

    # Apply LUT
    for i in range(length):
        dst[i] = lut[src[i]]

    return dst


def threshold(data: NDArray[np.uint8], thresh: int) -> NDArray[np.uint8]:
    """Binary threshold: values > thresh become 255, else 0."""
    return np.where(data > thresh, np.uint8(255), np.uint8(0))


def correlation(data1: NDArray[np.uint8], data2: NDArray[np.uint8]) -> float:
    """Fraction of matching elements between two arrays."""
    length = min(len(data1), len(data2))
    count = int(np.sum(data1[:length] == data2[:length]))
    return count / max(len(data1), len(data2))


def resize_eye(eye: Eye, resize_width: int, resize_height: int) -> Eye:
    """Resize an eye patch to the desired resolution using OpenCV."""
    import cv2

    # Reshape patch to (H, W, 4) RGBA
    rgba = eye.patch.reshape(eye.height, eye.width, 4) if eye.patch.ndim == 1 else eye.patch
    resized = cv2.resize(rgba, (resize_width, resize_height), interpolation=cv2.INTER_LINEAR)
    return Eye(resized.ravel(), eye.imagex, eye.imagey, resize_width, resize_height)


def bound(prediction: dict, screen_width: int, screen_height: int) -> dict:
    """Constrain prediction to screen boundaries."""
    x = max(0, min(prediction["x"], screen_width))
    y = max(0, min(prediction["y"], screen_height))
    return {"x": x, "y": y}


# ---------------------------------------------------------------------------
# Kalman Filter
# ---------------------------------------------------------------------------

class KalmanFilter:
    """Simple Kalman filter for smoothing bounding box positions."""

    def __init__(
        self,
        F: NDArray[np.float64],
        H: NDArray[np.float64],
        Q: NDArray[np.float64],
        R: NDArray[np.float64],
        P_initial: NDArray[np.float64],
        X_initial: NDArray[np.float64],
    ):
        self.F = np.array(F, dtype=np.float64)
        self.Q = np.array(Q, dtype=np.float64)
        self.H = np.array(H, dtype=np.float64)
        self.R = np.array(R, dtype=np.float64)
        self.P = np.array(P_initial, dtype=np.float64)
        self.X = np.array(X_initial, dtype=np.float64)

    def update(self, z: list[float]) -> list[float]:
        z_col = np.array(z, dtype=np.float64).reshape(-1, 1)

        # Prediction
        X_p = self.F @ self.X
        P_p = self.F @ self.P @ self.F.T + self.Q

        # Update
        y = z_col - self.H @ X_p
        S = self.H @ P_p @ self.H.T + self.R
        K = P_p @ self.H.T @ np.linalg.inv(S)

        self.X = X_p + K @ y
        self.P = (np.eye(K.shape[0]) - K @ self.H) @ P_p

        result = (self.H @ self.X).flatten().tolist()
        return result
