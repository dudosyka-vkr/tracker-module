"""Tests for offline fixation detection algorithms (I-DT, I-VT, Hybrid)."""

from eyetracker.core.fixation_offline import (
    detect_fixations_hybrid,
    detect_fixations_idt,
    detect_fixations_ivt,
)


def _cluster(cx, cy, n, start_ms, step_ms=50, jitter=1.0):
    """Generate *n* points clustered around (cx, cy) with small jitter."""
    pts = []
    for i in range(n):
        pts.append({
            "x": cx + (i % 3) * jitter,
            "y": cy + (i % 2) * jitter,
            "time_ms": start_ms + i * step_ms,
        })
    return pts


def _jump(x1, y1, x2, y2, t):
    """Single high-velocity point pair (saccade)."""
    return [
        {"x": x1, "y": y1, "time_ms": t},
        {"x": x2, "y": y2, "time_ms": t + 10},
    ]


# ---- Common return format ------------------------------------------------


def _check_fixation_format(fix):
    assert "center" in fix
    assert "x" in fix["center"] and "y" in fix["center"]
    assert "radius" in fix and fix["radius"] >= 0
    assert "start_ms" in fix
    assert "end_ms" in fix
    assert "duration_ms" in fix
    assert fix["duration_ms"] == fix["end_ms"] - fix["start_ms"]
    assert "points" in fix and len(fix["points"]) >= 2
    assert "is_first" in fix


# ---- I-DT Tests ---------------------------------------------------------


class TestIDT:
    def test_single_cluster(self):
        pts = _cluster(100, 200, 20, start_ms=0, step_ms=50)
        result = detect_fixations_idt(pts, dispersion_threshold=50, min_duration_ms=100)
        assert len(result) == 1
        _check_fixation_format(result[0])
        assert result[0]["is_first"] is True
        assert abs(result[0]["center"]["x"] - 100) < 5
        assert abs(result[0]["center"]["y"] - 200) < 5

    def test_two_clusters(self):
        pts = _cluster(100, 100, 15, start_ms=0)
        pts += _jump(100, 100, 500, 500, pts[-1]["time_ms"] + 50)
        pts += _cluster(500, 500, 15, start_ms=pts[-1]["time_ms"] + 50)
        result = detect_fixations_idt(pts, dispersion_threshold=50, min_duration_ms=100)
        assert len(result) == 2
        assert result[0]["is_first"] is True
        assert result[1]["is_first"] is False

    def test_spread_points_no_fixation(self):
        pts = [{"x": i * 200.0, "y": 0.0, "time_ms": i * 50} for i in range(20)]
        result = detect_fixations_idt(pts, dispersion_threshold=50, min_duration_ms=100)
        assert len(result) == 0

    def test_empty_input(self):
        assert detect_fixations_idt([]) == []

    def test_too_few_points(self):
        assert detect_fixations_idt([{"x": 0, "y": 0, "time_ms": 0}]) == []

    def test_short_fixation_filtered(self):
        pts = _cluster(100, 100, 3, start_ms=0, step_ms=10)
        result = detect_fixations_idt(pts, dispersion_threshold=50, min_duration_ms=100)
        assert len(result) == 0

    def test_duration_correct(self):
        pts = _cluster(100, 100, 10, start_ms=1000, step_ms=50)
        result = detect_fixations_idt(pts, dispersion_threshold=50, min_duration_ms=100)
        assert len(result) == 1
        fix = result[0]
        assert fix["start_ms"] == 1000
        assert fix["end_ms"] == 1000 + 9 * 50
        assert fix["duration_ms"] == 9 * 50


# ---- I-VT Tests ---------------------------------------------------------


class TestIVT:
    def test_single_cluster(self):
        pts = _cluster(100, 200, 20, start_ms=0, step_ms=50)
        result = detect_fixations_ivt(pts, velocity_threshold=0.5, min_duration_ms=100)
        assert len(result) == 1
        _check_fixation_format(result[0])
        assert result[0]["is_first"] is True

    def test_high_velocity_no_fixation(self):
        pts = []
        for i in range(20):
            pts.append({"x": i * 100.0, "y": 0.0, "time_ms": i * 10})
        result = detect_fixations_ivt(pts, velocity_threshold=0.5, min_duration_ms=100)
        assert len(result) == 0

    def test_two_clusters(self):
        pts = _cluster(100, 100, 15, start_ms=0)
        pts += _jump(100, 100, 800, 800, pts[-1]["time_ms"] + 50)
        pts += _cluster(800, 800, 15, start_ms=pts[-1]["time_ms"] + 50)
        result = detect_fixations_ivt(pts, velocity_threshold=0.5, min_duration_ms=100)
        assert len(result) == 2
        assert result[0]["is_first"] is True
        assert result[1]["is_first"] is False

    def test_empty_input(self):
        assert detect_fixations_ivt([]) == []

    def test_short_fixation_filtered(self):
        pts = _cluster(100, 100, 3, start_ms=0, step_ms=10)
        result = detect_fixations_ivt(pts, velocity_threshold=0.5, min_duration_ms=100)
        assert len(result) == 0

    def test_velocity_labels_correct(self):
        slow = _cluster(50, 50, 10, start_ms=0, step_ms=50)
        fast = [
            {"x": 50, "y": 50, "time_ms": 500},
            {"x": 500, "y": 500, "time_ms": 510},
        ]
        result = detect_fixations_ivt(slow + fast, velocity_threshold=0.5, min_duration_ms=100)
        assert len(result) == 1
        assert result[0]["end_ms"] <= 500


# ---- Hybrid Tests --------------------------------------------------------


class TestHybrid:
    def test_single_cluster(self):
        pts = _cluster(100, 200, 20, start_ms=0, step_ms=50)
        result = detect_fixations_hybrid(
            pts, velocity_threshold=0.5, dispersion_threshold=50, min_duration_ms=100,
        )
        assert len(result) == 1
        _check_fixation_format(result[0])
        assert result[0]["is_first"] is True

    def test_dispersed_slow_not_fixation(self):
        """Slow-moving but spatially dispersed points should not be a fixation."""
        pts = [{"x": i * 10.0, "y": 0.0, "time_ms": i * 200} for i in range(20)]
        result = detect_fixations_hybrid(
            pts, velocity_threshold=0.5, dispersion_threshold=30, min_duration_ms=100,
        )
        assert len(result) == 0

    def test_two_clusters(self):
        pts = _cluster(100, 100, 15, start_ms=0)
        pts += _jump(100, 100, 800, 800, pts[-1]["time_ms"] + 50)
        pts += _cluster(800, 800, 15, start_ms=pts[-1]["time_ms"] + 50)
        result = detect_fixations_hybrid(
            pts, velocity_threshold=0.5, dispersion_threshold=50, min_duration_ms=100,
        )
        assert len(result) == 2

    def test_empty_input(self):
        assert detect_fixations_hybrid([]) == []

    def test_hybrid_stricter_than_ivt(self):
        """Hybrid should produce fewer or equal fixations compared to I-VT alone,
        because it applies an additional dispersion filter."""
        pts = [{"x": i * 8.0, "y": 0.0, "time_ms": i * 200} for i in range(20)]
        ivt_result = detect_fixations_ivt(pts, velocity_threshold=0.5, min_duration_ms=100)
        hybrid_result = detect_fixations_hybrid(
            pts, velocity_threshold=0.5, dispersion_threshold=30, min_duration_ms=100,
        )
        assert len(hybrid_result) <= len(ivt_result)
