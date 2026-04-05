"""Face emotion recognition stub."""

from __future__ import annotations

import random

EMOTIONS: list[str] = [
    "neutral",
    "happy",
    "sad",
    "angry",
    "surprised",
    "fear",
    "disgust",
]


class FaceEmotionRecognition:
    """Returns a random emotion label for a given gaze point.

    This is a mock implementation. Replace with a real model when available.
    Accepts an optional ``rng`` (``random.Random`` instance) for deterministic
    results in tests.
    """

    def __init__(self, rng: random.Random | None = None):
        self._rng = rng or random.Random()

    def get_emotion_at(self, x: float, y: float) -> str:
        """Return one of the predefined emotion labels."""
        return self._rng.choice(EMOTIONS)
