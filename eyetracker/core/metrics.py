"""Gaze metrics aggregation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GazePoint:
    """Single gaze point in normalized 0..1 coordinates."""

    x: float
    y: float


@dataclass
class AggregatedGroup:
    """Average gaze position over a group of consecutive points."""

    x: float
    y: float
    count: int


class GazeMetricsAggregator:
    """Collects gaze points and groups them into averaged chunks."""

    def __init__(self, group_size: int = 1):
        self._group_size = group_size
        self._points: list[GazePoint] = []

    def add_point(self, x_px: float, y_px: float, screen_w: int, screen_h: int) -> None:
        """Normalize pixel coordinates to 0..1 and store."""
        nx = x_px / screen_w if screen_w > 0 else 0.0
        ny = y_px / screen_h if screen_h > 0 else 0.0
        self._points.append(GazePoint(x=nx, y=ny))

    def get_aggregated(self) -> list[AggregatedGroup]:
        """Return averaged groups of consecutive points."""
        if not self._points:
            return []

        result: list[AggregatedGroup] = []
        for i in range(0, len(self._points), self._group_size):
            chunk = self._points[i : i + self._group_size]
            avg_x = sum(p.x for p in chunk) / len(chunk)
            avg_y = sum(p.y for p in chunk) / len(chunk)
            result.append(AggregatedGroup(x=avg_x, y=avg_y, count=len(chunk)))
        return result

    def reset(self) -> None:
        """Clear all stored points."""
        self._points.clear()
