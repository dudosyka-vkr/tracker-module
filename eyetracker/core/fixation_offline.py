"""Offline fixation detection from timed gaze point sequences.

Three algorithms are provided, all sharing the same return format:

- **I-DT** (Identification by Dispersion Threshold): groups points whose spatial
  dispersion stays below a threshold into fixations.
- **I-VT** (Identification by Velocity Threshold): classifies points by
  point-to-point velocity; low-velocity runs become fixations.
- **Hybrid** (I-VT + I-DT): uses velocity to find non-saccade intervals,
  then validates each with a dispersion check.

Each function accepts ``points`` — a list of dicts with keys ``"x"``, ``"y"``,
``"time_ms"`` — and returns a list of fixation dicts.
"""

from __future__ import annotations

import math


def _centroid_and_radius(
    pts: list[dict],
) -> tuple[float, float, float]:
    """Return (cx, cy, max_radius) for a set of point dicts."""
    n = len(pts)
    cx = sum(p["x"] for p in pts) / n
    cy = sum(p["y"] for p in pts) / n
    radius = max(math.hypot(p["x"] - cx, p["y"] - cy) for p in pts)
    return cx, cy, radius


def _make_fixation(pts: list[dict], is_first: bool) -> dict:
    """Build a fixation dict from a list of gaze point dicts."""
    cx, cy, radius = _centroid_and_radius(pts)
    return {
        "center": {"x": cx, "y": cy},
        "radius": radius,
        "start_ms": pts[0]["time_ms"],
        "end_ms": pts[-1]["time_ms"],
        "duration_ms": pts[-1]["time_ms"] - pts[0]["time_ms"],
        "points": [{"x": p["x"], "y": p["y"], "time_ms": p["time_ms"]} for p in pts],
        "is_first": is_first,
    }


def _tag_first(fixations: list[dict]) -> list[dict]:
    """Set ``is_first`` on the first fixation, False on all others."""
    for i, f in enumerate(fixations):
        f["is_first"] = i == 0
    return fixations


# ---------------------------------------------------------------------------
# I-DT  (Identification by Dispersion Threshold)
# ---------------------------------------------------------------------------


def detect_fixations_idt(
    points: list[dict],
    dispersion_threshold: float = 80.0,
    min_duration_ms: int = 100,
    window_size: int = 10,
) -> list[dict]:
    """Detect fixations using an expanding-window dispersion algorithm.

    Starting from each unprocessed point, the window expands as long as the
    maximum distance of any point from the centroid stays below
    *dispersion_threshold*.  When the dispersion exceeds the threshold (or the
    points are exhausted), the accumulated window is finalized as a fixation if
    its duration >= *min_duration_ms*.

    Args:
        points: Gaze samples, each with ``x``, ``y``, ``time_ms``.
        dispersion_threshold: Max allowed radius (px) for a fixation cluster.
        min_duration_ms: Minimum fixation duration to keep.
        window_size: Initial window size (samples) before expansion begins.

    Returns:
        List of fixation dicts.
    """
    if len(points) < 2:
        return []

    fixations: list[dict] = []
    i = 0
    n = len(points)

    while i < n:
        # Start a candidate window
        j = min(i + window_size, n)
        if j - i < 2:
            break

        window = list(points[i:j])
        _, _, radius = _centroid_and_radius(window)

        if radius >= dispersion_threshold:
            i += 1
            continue

        # Expand window while dispersion stays below threshold
        while j < n:
            window.append(points[j])
            _, _, radius = _centroid_and_radius(window)
            if radius >= dispersion_threshold:
                window.pop()
                break
            j += 1

        duration = window[-1]["time_ms"] - window[0]["time_ms"]
        if duration >= min_duration_ms:
            fixations.append(_make_fixation(window, is_first=False))

        i = j  # skip past consumed points

    return _tag_first(fixations)


# ---------------------------------------------------------------------------
# I-VT  (Identification by Velocity Threshold)
# ---------------------------------------------------------------------------


def detect_fixations_ivt(
    points: list[dict],
    velocity_threshold: float = 0.5,
    min_duration_ms: int = 100,
) -> list[dict]:
    """Detect fixations using point-to-point velocity classification.

    Each point is labeled as fixation or saccade based on the velocity to its
    successor.  Consecutive fixation-labeled points are grouped; groups with
    duration >= *min_duration_ms* become fixations.

    Args:
        points: Gaze samples, each with ``x``, ``y``, ``time_ms``.
        velocity_threshold: Max velocity (px/ms) for a fixation sample.
        min_duration_ms: Minimum fixation duration to keep.

    Returns:
        List of fixation dicts.
    """
    if len(points) < 2:
        return []

    # Label each point by velocity to its neighbor
    labels = []  # True = fixation-like, False = saccade-like
    for k in range(len(points) - 1):
        p1, p2 = points[k], points[k + 1]
        dt = p2["time_ms"] - p1["time_ms"]
        if dt <= 0:
            labels.append(True)
            continue
        dist = math.hypot(p2["x"] - p1["x"], p2["y"] - p1["y"])
        vel = dist / dt
        labels.append(vel < velocity_threshold)
    # Last point inherits label of its predecessor
    labels.append(labels[-1] if labels else True)

    # Group consecutive fixation-labeled points
    fixations: list[dict] = []
    group_start = None
    for k, is_fix in enumerate(labels):
        if is_fix:
            if group_start is None:
                group_start = k
        else:
            if group_start is not None:
                segment = points[group_start: k]
                if len(segment) >= 2:
                    duration = segment[-1]["time_ms"] - segment[0]["time_ms"]
                    if duration >= min_duration_ms:
                        fixations.append(_make_fixation(segment, is_first=False))
                group_start = None

    # Flush trailing group
    if group_start is not None:
        segment = points[group_start:]
        if len(segment) >= 2:
            duration = segment[-1]["time_ms"] - segment[0]["time_ms"]
            if duration >= min_duration_ms:
                fixations.append(_make_fixation(segment, is_first=False))

    return _tag_first(fixations)


# ---------------------------------------------------------------------------
# Hybrid  (I-VT segmentation  +  I-DT validation)
# ---------------------------------------------------------------------------


def detect_fixations_hybrid(
    points: list[dict],
    velocity_threshold: float = 0.5,
    dispersion_threshold: float = 80.0,
    min_duration_ms: int = 100,
) -> list[dict]:
    """Detect fixations using velocity segmentation validated by dispersion.

    First, I-VT velocity classification identifies non-saccade intervals.
    Then each interval is checked: only those whose spatial dispersion is below
    *dispersion_threshold* are kept as fixations.

    Args:
        points: Gaze samples, each with ``x``, ``y``, ``time_ms``.
        velocity_threshold: Max velocity (px/ms) for non-saccade classification.
        dispersion_threshold: Max allowed radius (px) for fixation validation.
        min_duration_ms: Minimum fixation duration to keep.

    Returns:
        List of fixation dicts.
    """
    if len(points) < 2:
        return []

    # Step 1: velocity labels
    labels = []
    for k in range(len(points) - 1):
        p1, p2 = points[k], points[k + 1]
        dt = p2["time_ms"] - p1["time_ms"]
        if dt <= 0:
            labels.append(True)
            continue
        dist = math.hypot(p2["x"] - p1["x"], p2["y"] - p1["y"])
        vel = dist / dt
        labels.append(vel < velocity_threshold)
    labels.append(labels[-1] if labels else True)

    # Step 2: group non-saccade intervals, validate with dispersion
    fixations: list[dict] = []
    group_start = None
    for k, is_fix in enumerate(labels):
        if is_fix:
            if group_start is None:
                group_start = k
        else:
            if group_start is not None:
                segment = points[group_start: k]
                if len(segment) >= 2:
                    _, _, radius = _centroid_and_radius(segment)
                    duration = segment[-1]["time_ms"] - segment[0]["time_ms"]
                    if radius < dispersion_threshold and duration >= min_duration_ms:
                        fixations.append(_make_fixation(segment, is_first=False))
                group_start = None

    if group_start is not None:
        segment = points[group_start:]
        if len(segment) >= 2:
            _, _, radius = _centroid_and_radius(segment)
            duration = segment[-1]["time_ms"] - segment[0]["time_ms"]
            if radius < dispersion_threshold and duration >= min_duration_ms:
                fixations.append(_make_fixation(segment, is_first=False))

    return _tag_first(fixations)
