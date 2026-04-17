"""Tests for GazeMetricsAggregator."""

from eyetracker.core.metrics import GazeMetricsAggregator


def test_normalization():
    agg = GazeMetricsAggregator(group_size=1)
    agg.add_point(500, 300, 1000, 600)
    groups = agg.get_aggregated()
    assert len(groups) == 1
    assert abs(groups[0].x - 0.5) < 1e-9
    assert abs(groups[0].y - 0.5) < 1e-9
    assert groups[0].count == 1


def test_grouping_25_points():
    agg = GazeMetricsAggregator(group_size=10)
    for _ in range(25):
        agg.add_point(100, 200, 1000, 1000)
    groups = agg.get_aggregated()
    assert len(groups) == 3
    assert groups[0].count == 10
    assert groups[1].count == 10
    assert groups[2].count == 5


def test_empty():
    agg = GazeMetricsAggregator()
    assert agg.get_aggregated() == []


def test_reset():
    agg = GazeMetricsAggregator()
    agg.add_point(100, 100, 200, 200)
    assert len(agg.get_aggregated()) == 1
    agg.reset()
    assert agg.get_aggregated() == []


def test_group_averages():
    agg = GazeMetricsAggregator(group_size=2)
    agg.add_point(0, 0, 100, 100)      # (0.0, 0.0)
    agg.add_point(100, 100, 100, 100)  # (1.0, 1.0)
    groups = agg.get_aggregated()
    assert len(groups) == 1
    assert abs(groups[0].x - 0.5) < 1e-9
    assert abs(groups[0].y - 0.5) < 1e-9
    assert groups[0].count == 2
