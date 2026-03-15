"""Tests for precision calculator."""

from eyetracker.ui.pages.calibration import PrecisionCalculator


class TestPrecisionCalculator:
    def test_perfect_accuracy(self):
        pc = PrecisionCalculator(window_size=10)
        pc.start_storing()
        for _ in range(10):
            pc.store_point(500.0, 400.0)
        pc.stop_storing()
        accuracy = pc.calculate_precision(500.0, 400.0)
        assert accuracy == 100.0

    def test_zero_predictions(self):
        pc = PrecisionCalculator()
        accuracy = pc.calculate_precision(500.0, 400.0)
        assert accuracy == 0.0

    def test_some_distance(self):
        pc = PrecisionCalculator(window_size=10)
        pc.start_storing()
        for i in range(10):
            pc.store_point(500.0 + i * 10, 400.0)
        pc.stop_storing()
        accuracy = pc.calculate_precision(500.0, 400.0)
        assert 0 < accuracy < 100

    def test_get_points(self):
        pc = PrecisionCalculator(window_size=5)
        pc.start_storing()
        pc.store_point(1.0, 2.0)
        pc.store_point(3.0, 4.0)
        xs, ys = pc.get_points()
        assert xs == [1.0, 3.0]
        assert ys == [2.0, 4.0]
