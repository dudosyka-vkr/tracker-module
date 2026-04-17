"""Tests for FixationDetector."""

from eyetracker.core.fixation import FixationDetector


def _make_detector(k=50.0, window_samples=10, min_points=4, events=None):
    collected = [] if events is None else events
    d = FixationDetector(
        k=k,
        window_size_samples=window_samples,
        min_points=min_points,
        on_fixation=collected.append,
    )
    return d, collected


def test_detects_fixation():
    """Clustered points within radius < K trigger exactly one fixation event."""
    d, events = _make_detector(k=50.0, min_points=4)
    for _ in range(6):
        d.on_gaze_point(100.0, 200.0)

    assert len(events) == 1
    ev = events[0]
    assert ev["k"] == 50.0
    assert abs(ev["center"]["x"] - 100.0) < 1e-9
    assert abs(ev["center"]["y"] - 200.0) < 1e-9
    assert ev["radius"] < 50.0
    assert len(ev["window_points"]) >= 4


def test_no_fixation_for_spread_points():
    """Points spread beyond K do not trigger a fixation event."""
    d, events = _make_detector(k=50.0, min_points=4)
    xs = [0.0, 200.0, 0.0, 200.0, 0.0, 200.0]
    for x in xs:
        d.on_gaze_point(x, 0.0)

    assert len(events) == 0


def test_first_fixation_flag():
    """The consumer correctly marks only the first fixation with is_first=True."""
    # window=4 samples, min_points=4: buffer always holds last 4 points
    d, events = _make_detector(k=50.0, window_samples=4, min_points=4)

    # First cluster: 4 clustered points → fixation fires
    for _ in range(4):
        d.on_gaze_point(100.0, 100.0)

    # Exit: 4 spread points push out the clustered ones (radius > k*1.2=60)
    for i in range(4):
        d.on_gaze_point(0.0 if i % 2 == 0 else 200.0, 100.0)

    # Second cluster: 4 fresh clustered points → fixation fires again
    for _ in range(4):
        d.on_gaze_point(300.0, 300.0)

    assert len(events) == 2

    # Simulate the consumer logic from TestRunScreen
    first_recorded = False
    for ev in events:
        ev["is_first"] = not first_recorded
        if not first_recorded:
            first_recorded = True

    assert events[0]["is_first"] is True
    assert events[1]["is_first"] is False


def test_debounce_state_machine():
    """Points that stay within the fixation zone do not re-fire the event."""
    d, events = _make_detector(k=50.0, min_points=4)
    for _ in range(20):
        d.on_gaze_point(500.0, 500.0)

    assert len(events) == 1


def test_window_eviction():
    """Old points outside the sample window are evicted by the ring buffer."""
    # window=4, min_points=4: buffer holds exactly 4 points
    d, events = _make_detector(k=50.0, window_samples=4, min_points=4)

    # 3 clustered points — not enough to detect yet
    for _ in range(3):
        d.on_gaze_point(100.0, 100.0)

    # 4 spread points — each new point evicts oldest; buffer ends up all spread
    spread_xs = [0.0, 300.0, 0.0, 300.0]
    for x in spread_xs:
        d.on_gaze_point(x, 100.0)

    # No fixation: clustered points were evicted, only spread remain
    assert len(events) == 0
