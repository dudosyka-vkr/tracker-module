"""Tests for eyetracker.util module."""

import numpy as np
import pytest

from eyetracker.core.util import (
    DataWindow,
    Eye,
    grayscale,
    equalize_histogram,
    threshold,
    correlation,
    bound,
    KalmanFilter,
)


class TestDataWindow:
    def test_push_within_capacity(self):
        dw = DataWindow(5)
        for i in range(3):
            dw.push(i)
        assert dw.length == 3
        assert dw.get(0) == 0
        assert dw.get(2) == 2

    def test_push_wraps_around(self):
        dw = DataWindow(3)
        for i in range(5):
            dw.push(i)
        assert dw.length == 3
        # After pushing 0,1,2,3,4 with window size 3:
        # data = [3, 4, 2], index = 2
        # get(0) should return oldest = 2
        assert dw.get(0) == 2
        assert dw.get(1) == 3
        assert dw.get(2) == 4

    def test_init_with_data(self):
        dw = DataWindow(3, [10, 20, 30, 40, 50])
        assert dw.length == 3
        assert dw.data == [30, 40, 50]

    def test_add_all(self):
        dw = DataWindow(5)
        dw.add_all([1, 2, 3])
        assert dw.length == 3


class TestEye:
    def test_creation(self):
        patch = np.zeros(40, dtype=np.uint8)
        eye = Eye(patch, 10, 20, 5, 2)
        assert eye.width == 5
        assert eye.height == 2
        assert eye.imagex == 10
        assert eye.imagey == 20
        assert eye.blink is False
        assert eye.pupil is None


class TestGrayscale:
    def test_pure_red(self):
        # 1 pixel RGBA: (255, 0, 0, 255)
        rgba = np.array([255, 0, 0, 255], dtype=np.uint8)
        gray = grayscale(rgba, 1, 1)
        # 0.299 * 255 ≈ 76
        assert gray[0] == 76

    def test_pure_white(self):
        rgba = np.array([255, 255, 255, 255], dtype=np.uint8)
        gray = grayscale(rgba, 1, 1)
        assert gray[0] == 254 or gray[0] == 255  # rounding

    def test_pure_black(self):
        rgba = np.array([0, 0, 0, 255], dtype=np.uint8)
        gray = grayscale(rgba, 1, 1)
        assert gray[0] == 0

    def test_shape(self):
        rgba = np.zeros(4 * 3 * 2, dtype=np.uint8)  # 3x2 image
        gray = grayscale(rgba, 3, 2)
        assert len(gray) == 6


class TestEqualizeHistogram:
    def test_output_length(self):
        src = np.random.randint(0, 256, size=100, dtype=np.uint8)
        dst = equalize_histogram(src, 5)
        assert len(dst) == 100

    def test_all_same_value(self):
        src = np.full(100, 128, dtype=np.uint8)
        dst = equalize_histogram(src, 1)
        # All pixels same → all map to 255
        assert np.all(dst == 255)


class TestThreshold:
    def test_basic(self):
        data = np.array([50, 100, 150, 200], dtype=np.uint8)
        result = threshold(data, 120)
        np.testing.assert_array_equal(result, [0, 0, 255, 255])


class TestCorrelation:
    def test_identical(self):
        a = np.array([1, 2, 3], dtype=np.uint8)
        assert correlation(a, a) == 1.0

    def test_different(self):
        a = np.array([0, 0, 0], dtype=np.uint8)
        b = np.array([1, 1, 1], dtype=np.uint8)
        assert correlation(a, b) == 0.0


class TestBound:
    def test_within_bounds(self):
        result = bound({"x": 100, "y": 200}, 1920, 1080)
        assert result == {"x": 100, "y": 200}

    def test_negative_values(self):
        result = bound({"x": -10, "y": -5}, 1920, 1080)
        assert result == {"x": 0, "y": 0}

    def test_exceeds_bounds(self):
        result = bound({"x": 2000, "y": 1200}, 1920, 1080)
        assert result == {"x": 1920, "y": 1080}


class TestKalmanFilter:
    def test_basic_update(self):
        F = np.eye(2).tolist()
        H = np.eye(2).tolist()
        Q = (np.eye(2) * 0.1).tolist()
        R = (np.eye(2) * 1.0).tolist()
        P = np.eye(2).tolist()
        X = [[0.0], [0.0]]

        kf = KalmanFilter(F, H, Q, R, P, X)
        result = kf.update([1.0, 1.0])
        # Should move toward measurement
        assert len(result) == 2
        assert result[0] > 0
        assert result[1] > 0
