"""Tests for regression models."""

import numpy as np
import pytest

from eyetracker.core.util import Eye
from eyetracker.core.pipeline import _ridge, _get_eye_feats, RidgeWeightedReg


def _make_eye(width=20, height=15) -> Eye:
    """Create a fake eye patch for testing."""
    patch = np.random.randint(0, 256, size=width * height * 4, dtype=np.uint8)
    return Eye(patch, 0, 0, width, height)


class TestRidgeFunction:
    def test_simple_fit(self):
        # y = 2*x1 + 3*x2
        X = np.array([[1, 0], [0, 1], [1, 1], [2, 1]], dtype=np.float64)
        y = np.array([[2], [3], [5], [7]], dtype=np.float64)
        coeff = _ridge(y, X, 1e-5)
        assert np.allclose(coeff, [2, 3], atol=0.1)


class TestRidgeWeightedReg:
    def test_add_data_and_predict(self):
        reg = RidgeWeightedReg()
        for _ in range(10):
            left = _make_eye()
            right = _make_eye()
            reg.add_data(left, right, [500.0, 300.0], "click")

        left = _make_eye()
        right = _make_eye()
        result = reg.predict(left, right)
        assert result is not None
        assert "x" in result
        assert "y" in result

    def test_predict_with_no_data_returns_none(self):
        reg = RidgeWeightedReg()
        left = _make_eye()
        right = _make_eye()
        assert reg.predict(left, right) is None

    def test_get_eye_feats_length(self):
        left = _make_eye()
        right = _make_eye()
        feats = _get_eye_feats(left, right)
        # 10*6 per eye * 2 eyes = 120
        assert len(feats) == 120


class TestGetEyeFeats:
    def test_deterministic(self):
        """Same input should produce same output."""
        patch = np.full(20 * 15 * 4, 128, dtype=np.uint8)
        left = Eye(patch.copy(), 0, 0, 20, 15)
        right = Eye(patch.copy(), 0, 0, 20, 15)
        feats1 = _get_eye_feats(left, right)

        left2 = Eye(patch.copy(), 0, 0, 20, 15)
        right2 = Eye(patch.copy(), 0, 0, 20, 15)
        feats2 = _get_eye_feats(left2, right2)

        assert feats1 == feats2
