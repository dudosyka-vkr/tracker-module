"""Real-time fixation detection using a sample-count sliding window."""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Callable


@dataclass
class _Point:
    x: float
    y: float


class FixationDetector:
    """Detects fixations in a gaze point stream using a fixed-size sample window.

    Algorithm:
    - Maintains a ring buffer of the last ``window_size_samples`` gaze points.
    - Detection begins only once the buffer has at least ``min_points`` entries.
    - Computes centroid center and max-distance radius over the buffer.
    - Fixation is entered when ``radius < k``.
    - Fixation is exited when ``radius > k * exit_hysteresis_factor``.
    - ``on_fixation`` is called exactly once on the not-fixating→fixating
      transition with a payload dict.

    Coordinates are in screen pixels; ``k`` must be in the same units.
    """

    def __init__(
        self,
        k: float,
        window_size_samples: int = 10,
        min_points: int = 6,
        exit_hysteresis_factor: float = 1.2,
        on_fixation: Callable[[dict], None] | None = None,
    ):
        self._k = k
        self._min_points = min_points
        self._exit_k = k * exit_hysteresis_factor
        self._on_fixation = on_fixation
        self._buffer: deque[_Point] = deque(maxlen=window_size_samples)
        self._is_fixating = False

    def reset(self) -> None:
        """Clear buffer and reset fixation state (call at start of each image)."""
        self._buffer.clear()
        self._is_fixating = False

    def on_gaze_point(self, x: float, y: float) -> None:
        """Feed a new gaze point; triggers ``on_fixation`` when fixation is detected."""
        if not math.isfinite(x) or not math.isfinite(y):
            return

        self._buffer.append(_Point(x=x, y=y))

        if len(self._buffer) < self._min_points:
            return

        n = len(self._buffer)
        center_x = sum(p.x for p in self._buffer) / n
        center_y = sum(p.y for p in self._buffer) / n
        radius = max(
            math.hypot(p.x - center_x, p.y - center_y) for p in self._buffer
        )

        if not self._is_fixating and radius < self._k:
            self._is_fixating = True
            if self._on_fixation is not None:
                self._on_fixation({
                    "k": self._k,
                    "window_points": [{"x": p.x, "y": p.y} for p in self._buffer],
                    "center": {"x": center_x, "y": center_y},
                    "radius": radius,
                })
        elif self._is_fixating and radius > self._exit_k:
            self._is_fixating = False
