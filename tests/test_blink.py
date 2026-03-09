"""Tests for blink detection."""

import numpy as np
import pytest

from eyetracker.util import Eye
from eyetracker.pipeline import BlinkDetector


def _make_eye(value: int = 128) -> Eye:
    patch = np.full(20 * 15 * 4, value, dtype=np.uint8)
    return Eye(patch, 0, 0, 20, 15)


class TestBlinkDetector:
    def test_no_blink_when_disabled(self):
        bd = BlinkDetector()
        left = _make_eye()
        right = _make_eye()
        bd.detect_blink(left, right, blink_detection_on=False)
        assert left.blink is False
        assert right.blink is False

    def test_no_blink_insufficient_data(self):
        bd = BlinkDetector(blink_window=8)
        for _ in range(3):
            left = _make_eye()
            right = _make_eye()
            bd.detect_blink(left, right, blink_detection_on=True)
        assert left.blink is False

    def test_identical_frames_no_blink(self):
        """Identical frames should have correlation ~1.0, so no blink."""
        bd = BlinkDetector(blink_window=4)
        for _ in range(10):
            left = _make_eye(128)
            right = _make_eye(128)
            bd.detect_blink(left, right, blink_detection_on=True)
        # Identical frames → correlation = 1.0 → above MAX_CORRELATION → no blink
        assert right.blink is False
