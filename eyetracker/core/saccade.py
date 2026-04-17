"""Saccade detection from gaze point sequences."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class Saccade:
    start_idx: int
    end_idx: int
    start_x: float
    start_y: float
    end_x: float
    end_y: float
    duration_ms: float | None  # None when no time_ms in data


def detect_saccades(
    gaze_groups: list[dict],
    velocities: list[float],
    *,
    threshold_factor: float = 1.0,
    min_duration_ms: float = 250.0,
) -> list[Saccade]:
    """Detect saccades based on velocity threshold.

    A saccade starts at the first point whose velocity exceeds
    ``mean + threshold_factor * std`` and ends at the next point whose
    velocity drops back to or below the mean.

    Args:
        gaze_groups: List of ``{"x": float, "y": float, ...}`` dicts.
        velocities: Per-point velocities returned by ``_compute_velocities``.
        threshold_factor: Multiplier of std added to mean to form the
            high-velocity threshold (default 1.0).

    Returns:
        List of :class:`Saccade` objects ordered by start index.
    """
    if len(velocities) < 2:
        return []

    non_zero = [v for v in velocities[1:] if v > 0]
    if not non_zero:
        return []

    mean_v = sum(non_zero) / len(non_zero)
    variance = sum((v - mean_v) ** 2 for v in non_zero) / len(non_zero)
    std_v = math.sqrt(variance)

    high_threshold = mean_v + threshold_factor * std_v
    low_threshold = mean_v

    saccades: list[Saccade] = []
    in_saccade = False
    saccade_start = 0

    for i, v in enumerate(velocities):
        if not in_saccade:
            if v > high_threshold:
                in_saccade = True
                saccade_start = i
        else:
            if v <= low_threshold:
                s = _make_saccade(gaze_groups, saccade_start, i)
                if _passes_duration_filter(s, min_duration_ms):
                    saccades.append(s)
                in_saccade = False

    if in_saccade and saccade_start < len(gaze_groups) - 1:
        s = _make_saccade(gaze_groups, saccade_start, len(gaze_groups) - 1)
        if _passes_duration_filter(s, min_duration_ms):
            saccades.append(s)

    return saccades


def _passes_duration_filter(saccade: Saccade, min_duration_ms: float) -> bool:
    """Return True if the saccade meets the minimum duration requirement."""
    if saccade.duration_ms is None:
        return True  # no timing data — let it through
    return saccade.duration_ms >= min_duration_ms


def _make_saccade(gaze_groups: list[dict], start_idx: int, end_idx: int) -> Saccade:
    g_start = gaze_groups[start_idx]
    g_end = gaze_groups[end_idx]

    t_start = g_start.get("time_ms")
    t_end = g_end.get("time_ms")
    duration_ms: float | None = (
        float(t_end - t_start) if (t_start is not None and t_end is not None) else None
    )

    return Saccade(
        start_idx=start_idx,
        end_idx=end_idx,
        start_x=float(g_start["x"]),
        start_y=float(g_start["y"]),
        end_x=float(g_end["x"]),
        end_y=float(g_end["y"]),
        duration_ms=duration_ms,
    )
