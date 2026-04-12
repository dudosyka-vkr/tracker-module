"""Eye-tracking pipeline.

Combines face tracking (MediaPipe), blink detection, ridge regression,
and the main EyeTracker orchestrator into a single module.
"""

from __future__ import annotations

import json
import logging
import math
import os
import platform
import sys
import time
import threading
import urllib.request
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from eyetracker.core.util import (
    DataWindow,
    Eye,
    KalmanFilter,
    bound,
    correlation,
    equalize_histogram,
    grayscale,
    resize_eye,
    threshold,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MediaPipe Face Mesh eye landmark indices
# ---------------------------------------------------------------------------

# Left eye contour (from the viewer's perspective — right eye in the image)
LEFT_EYE_INDICES = [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246]
# Right eye contour
RIGHT_EYE_INDICES = [362, 382, 381, 380, 374, 373, 390, 249, 263, 466, 388, 387, 386, 385, 384, 398]

_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "face_landmarker/face_landmarker/float16/latest/face_landmarker.task"
)
_BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(__file__))
_PACKAGE_DIR = os.path.dirname(os.path.dirname(__file__))  # eyetracker/
_MODEL_DIR = os.path.join(_BASE_DIR, "eyetracker", "models") if hasattr(sys, "_MEIPASS") else os.path.join(_PACKAGE_DIR, "models")
_MODEL_PATH = os.path.join(_MODEL_DIR, "face_landmarker.task")


def _ensure_model() -> str:
    """Download the FaceLandmarker model if not already cached."""
    if os.path.isfile(_MODEL_PATH):
        return _MODEL_PATH
    os.makedirs(_MODEL_DIR, exist_ok=True)
    print(f"Загрузка модели FaceLandmarker в {_MODEL_PATH} ...")
    urllib.request.urlretrieve(_MODEL_URL, _MODEL_PATH)
    print("Загрузка завершена.")
    return _MODEL_PATH


# ---------------------------------------------------------------------------
# MediaPipeTracker
# ---------------------------------------------------------------------------

class MediaPipeTracker:
    """Face/eye tracker using MediaPipe FaceLandmarker."""

    name = "mediapipe"

    def __init__(self, smooth_eye_bb: bool = False):
        import mediapipe as mp

        model_path = _ensure_model()

        base_options = mp.tasks.BaseOptions(model_asset_path=model_path)
        options = mp.tasks.vision.FaceLandmarkerOptions(
            base_options=base_options,
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_faces=1,
            min_face_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self._landmarker = mp.tasks.vision.FaceLandmarker.create_from_options(options)
        self._mp = mp
        self._frame_ts = 0

        self.smooth_eye_bb = smooth_eye_bb
        self._init_kalman()
        self.last_positions = None

    def _init_kalman(self):
        F = [
            [1, 0, 0, 0, 1, 0],
            [0, 1, 0, 0, 0, 1],
            [0, 0, 1, 0, 1, 0],
            [0, 0, 0, 1, 0, 1],
            [0, 0, 0, 0, 1, 0],
            [0, 0, 0, 0, 0, 1],
        ]
        delta_t = 1 / 10
        Q = np.array([
            [1/4, 0, 0, 0, 1/2, 0],
            [0, 1/4, 0, 0, 0, 1/2],
            [0, 0, 1/4, 0, 1/2, 0],
            [0, 0, 0, 1/4, 0, 1/2],
            [1/2, 0, 1/2, 0, 1, 0],
            [0, 1/2, 0, 1/2, 0, 1],
        ]) * delta_t
        H = [
            [1, 0, 0, 0, 0, 0],
            [0, 1, 0, 0, 0, 0],
            [0, 0, 1, 0, 0, 0],
            [0, 0, 0, 1, 0, 0],
        ]
        pixel_error = 6.5
        R = np.eye(4) * pixel_error
        P_initial = np.eye(6) * 0.0001
        x_initial = [[200], [150], [250], [180], [0], [0]]

        self.left_kalman = KalmanFilter(F, H, Q.tolist(), R.tolist(), P_initial.tolist(), x_initial)
        self.right_kalman = KalmanFilter(F, H, Q.tolist(), R.tolist(), P_initial.tolist(), x_initial)

    def get_eye_patches(self, frame: np.ndarray) -> tuple[Eye, Eye, list] | None:
        """Extract left and right eye patches from a BGR video frame.

        Args:
            frame: BGR numpy array from cv2.VideoCapture

        Returns:
            (left_eye, right_eye, landmarks) or None if face not detected
        """
        h, w = frame.shape[:2]
        if w == 0 or h == 0:
            return None

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)

        self._frame_ts += 33  # ~30fps in milliseconds
        results = self._landmarker.detect_for_video(mp_image, self._frame_ts)

        if not results.face_landmarks:
            return None

        face = results.face_landmarks[0]
        landmarks = [(int(lm.x * w), int(lm.y * h)) for lm in face]

        left_eye = self._extract_eye_patch(frame, landmarks, LEFT_EYE_INDICES, self.left_kalman)
        right_eye = self._extract_eye_patch(frame, landmarks, RIGHT_EYE_INDICES, self.right_kalman)

        if left_eye is None or right_eye is None:
            return None

        self.last_positions = landmarks
        return left_eye, right_eye, landmarks

    def _extract_eye_patch(
        self,
        frame: np.ndarray,
        landmarks: list[tuple[int, int]],
        indices: list[int],
        kalman: KalmanFilter,
    ) -> Eye | None:
        """Extract a single eye patch from the frame."""
        h, w = frame.shape[:2]

        pts = [landmarks[i] for i in indices]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]

        x_min = max(0, min(xs))
        y_min = max(0, min(ys))
        x_max = min(w, max(xs))
        y_max = min(h, max(ys))

        # Apply Kalman smoothing if enabled
        if self.smooth_eye_bb:
            box = [x_min, y_min, x_max, y_max]
            smoothed = kalman.update(box)
            x_min = max(0, round(smoothed[0]))
            y_min = max(0, round(smoothed[1]))
            x_max = min(w, round(smoothed[2]))
            y_max = min(h, round(smoothed[3]))

        eye_w = x_max - x_min
        eye_h = y_max - y_min

        if eye_w <= 0 or eye_h <= 0:
            return None

        # Extract the patch and convert to RGBA
        bgr_patch = frame[y_min:y_max, x_min:x_max]
        rgba_patch = cv2.cvtColor(bgr_patch, cv2.COLOR_BGR2RGBA)

        return Eye(rgba_patch.ravel(), x_min, y_min, eye_w, eye_h)

    def reset(self):
        self._init_kalman()
        self.last_positions = None
        self._frame_ts = 0

    def close(self):
        self._landmarker.close()


# ---------------------------------------------------------------------------
# BlinkDetector
# ---------------------------------------------------------------------------

DEFAULT_WINDOW_SIZE = 8
EQUALIZE_STEP = 5
THRESHOLD_VALUE = 80
MIN_CORRELATION = 0.78
MAX_CORRELATION = 0.85


class BlinkDetector:
    def __init__(self, blink_window: int = DEFAULT_WINDOW_SIZE):
        self.blink_window = blink_window
        self.blink_data = DataWindow(blink_window)

    def _extract_blink_data(self, right_eye: Eye) -> dict:
        gray = grayscale(right_eye.patch, right_eye.width, right_eye.height)
        equalized = equalize_histogram(gray, EQUALIZE_STEP)
        thresholded = threshold(equalized, THRESHOLD_VALUE)
        return {
            "data": thresholded,
            "width": right_eye.width,
            "height": right_eye.height,
        }

    def _is_same_eye(self, old_eye: dict, new_eye: dict) -> bool:
        return old_eye["width"] == new_eye["width"] and old_eye["height"] == new_eye["height"]

    def _is_blink(self) -> bool:
        corr = 0.0
        for i in range(self.blink_window):
            data = self.blink_data.get(i)
            next_data = self.blink_data.get(i + 1)
            if not self._is_same_eye(data, next_data):
                return False
            corr += correlation(data["data"], next_data["data"])
        corr /= self.blink_window
        return MIN_CORRELATION < corr < MAX_CORRELATION

    def detect_blink(self, left: Eye, right: Eye, blink_detection_on: bool = False) -> None:
        """Detect blink and set blink flags on the Eye objects."""
        if not blink_detection_on:
            return

        data = self._extract_blink_data(right)
        self.blink_data.push(data)

        left.blink = False
        right.blink = False

        if self.blink_data.length < self.blink_window:
            return

        if self._is_blink():
            left.blink = True
            right.blink = True


# ---------------------------------------------------------------------------
# Ridge regression
# ---------------------------------------------------------------------------

RIDGE_PARAMETER = 1e-5
RESIZE_WIDTH = 10
RESIZE_HEIGHT = 6
DATA_WINDOW = 700
TRAIL_DATA_WINDOW = 10
MOVE_TICK_SIZE = 50  # ms


def _ridge(y: np.ndarray, X: np.ndarray, k: float) -> np.ndarray:
    """Perform ridge regression: solve (X'X + kI) * beta = X'y.

    Returns coefficient vector.
    """
    success = False
    while not success:
        try:
            xt = X.T
            ss = xt @ X
            nc = ss.shape[0]
            for i in range(nc):
                ss[i, i] += k
            bb = xt @ y

            if ss.shape[0] == ss.shape[1]:
                coefficients = np.linalg.solve(ss, bb)
            else:
                coefficients, _, _, _ = np.linalg.lstsq(ss, bb, rcond=None)

            success = True
        except np.linalg.LinAlgError:
            k *= 10

    return coefficients.flatten()


def _get_eye_feats(left: Eye, right: Eye) -> list[float]:
    """Extract 120D eye feature vector from left and right eye patches.

    Each eye is resized to 10x6, grayscaled, histogram-equalized, then concatenated.
    """
    resized_left = resize_eye(left, RESIZE_WIDTH, RESIZE_HEIGHT)
    resized_right = resize_eye(right, RESIZE_WIDTH, RESIZE_HEIGHT)

    left_gray = grayscale(resized_left.patch, resized_left.width, resized_left.height)
    right_gray = grayscale(resized_right.patch, resized_right.width, resized_right.height)

    hist_left = equalize_histogram(left_gray, 5)
    hist_right = equalize_histogram(right_gray, 5)

    return hist_left.tolist() + hist_right.tolist()


class RidgeWeightedReg:
    """Weighted ridge regression gaze predictor."""

    def __init__(self):
        self.screen_x_clicks = DataWindow(DATA_WINDOW)
        self.screen_y_clicks = DataWindow(DATA_WINDOW)
        self.eye_features_clicks = DataWindow(DATA_WINDOW)

        self.trail_time = 1000
        self.trail_data_window = self.trail_time // MOVE_TICK_SIZE
        self.screen_x_trail = DataWindow(TRAIL_DATA_WINDOW)
        self.screen_y_trail = DataWindow(TRAIL_DATA_WINDOW)
        self.eye_features_trail = DataWindow(TRAIL_DATA_WINDOW)
        self.trail_times = DataWindow(TRAIL_DATA_WINDOW)

    def add_data(self, left: Eye, right: Eye, screen_pos: list[float], event_type: str) -> None:
        if left.blink or right.blink:
            return

        if event_type == "click":
            self.screen_x_clicks.push([screen_pos[0]])
            self.screen_y_clicks.push([screen_pos[1]])
            self.eye_features_clicks.push(_get_eye_feats(left, right))
        elif event_type == "move":
            self.screen_x_trail.push([screen_pos[0]])
            self.screen_y_trail.push([screen_pos[1]])
            self.eye_features_trail.push(_get_eye_feats(left, right))
            self.trail_times.push(time.time() * 1000)

    def predict(self, left: Eye, right: Eye) -> dict[str, int] | None:
        if self.eye_features_clicks.length == 0:
            return None

        accept_time = time.time() * 1000 - self.trail_time
        trail_x = []
        trail_y = []
        trail_feat = []
        for i in range(min(self.trail_data_window, self.trail_times.length)):
            if self.trail_times.get(i) > accept_time:
                trail_x.append(self.screen_x_trail.get(i))
                trail_y.append(self.screen_y_trail.get(i))
                trail_feat.append(self.eye_features_trail.get(i))

        # Apply recency weighting to click data
        n = self.eye_features_clicks.length
        weighted_feats = []
        weighted_x = []
        weighted_y = []

        for i in range(n):
            weight = math.sqrt(1.0 / (n - i))
            true_idx = self.eye_features_clicks._true_index(i)
            feats = self.eye_features_clicks.data[true_idx]
            weighted_feats.append([f * weight for f in feats])
            weighted_x.append([self.screen_x_clicks.get(i)[0] * weight])
            weighted_y.append([self.screen_y_clicks.get(i)[0] * weight])

        screen_x = weighted_x + trail_x
        screen_y = weighted_y + trail_y
        eye_features = weighted_feats + trail_feat

        if len(eye_features) == 0:
            return None

        X = np.array(eye_features, dtype=np.float64)
        y_x = np.array(screen_x, dtype=np.float64)
        y_y = np.array(screen_y, dtype=np.float64)

        coeff_x = _ridge(y_x, X, RIDGE_PARAMETER)
        coeff_y = _ridge(y_y, X, RIDGE_PARAMETER)

        feats = np.array(_get_eye_feats(left, right), dtype=np.float64)
        predicted_x = int(np.floor(feats @ coeff_x))
        predicted_y = int(np.floor(feats @ coeff_y))

        return {"x": predicted_x, "y": predicted_y}


# ---------------------------------------------------------------------------
# EyeTracker orchestrator
# ---------------------------------------------------------------------------

class Params:
    """Configuration parameters for the eye-tracking pipeline."""

    def __init__(self):
        self.video_width = 640
        self.video_height = 480
        self.data_timestep = 50  # ms


class EyeTracker:
    """Main EyeTracker class — orchestrates the eye-tracking pipeline.

    Usage:
        wg = EyeTracker()
        wg.begin()
        # ... use wg.get_current_prediction() or set_gaze_listener()
        wg.end()
    """

    def __init__(self):
        self.params = Params()

        self._tracker = MediaPipeTracker(smooth_eye_bb=True)
        self._blink_detector = BlinkDetector()
        self._regs = [RidgeWeightedReg()]

        self._cap: cv2.VideoCapture | None = None
        self._camera_index: int = 0
        self._paused = True
        self._running = False
        self._loop_thread: threading.Thread | None = None
        self._empty_frame_count: int = 0

        self._latest_eye_features: tuple[Eye, Eye] | None = None
        self._latest_gaze: dict | None = None
        self._latest_frame: np.ndarray | None = None
        self._latest_landmarks: list | None = None

        self._smoothing = DataWindow(4)
        self.smoothing_window_size = 4
        self._callback: Callable | None = None
        self._clock_start = 0.0

        self._screen_width = 1920
        self._screen_height = 1080

    def set_screen_size(self, width: int, height: int) -> "EyeTracker":
        self._screen_width = width
        self._screen_height = height
        return self

    def _open_capture(self, camera_index: int) -> cv2.VideoCapture | None:
        if platform.system() == "Darwin":
            cap = cv2.VideoCapture(camera_index, cv2.CAP_AVFOUNDATION)
        else:
            cap = cv2.VideoCapture(camera_index)
        if not cap.isOpened():
            return None
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.params.video_width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.params.video_height)
        return cap

    def begin(self, camera_index: int = 0) -> "EyeTracker":
        """Start webcam capture and the prediction loop."""
        self._camera_index = camera_index
        self._cap = self._open_capture(camera_index)

        if not self._cap:
            logger.error("Could not open webcam at index %d", camera_index)
            return self

        # Warmup: let the camera initialize and deliver first frames
        for _ in range(5):
            self._cap.read()

        self._paused = False
        self._running = True
        self._clock_start = time.time()

        self._loop_thread = threading.Thread(target=self._loop, daemon=True)
        self._loop_thread.start()

        logger.info("Eye tracker started")
        return self

    def pause(self) -> "EyeTracker":
        self._paused = True
        return self

    def resume(self) -> "EyeTracker":
        if not self._paused:
            return self
        self._paused = False
        return self

    def end(self) -> "EyeTracker":
        """Stop the prediction loop and release webcam."""
        self._paused = True
        self._running = False
        if self._loop_thread:
            self._loop_thread.join(timeout=2)
        if self._cap:
            self._cap.release()
            self._cap = None
        self._tracker.close()
        logger.info("Eye tracker stopped")
        return self

    def set_gaze_listener(self, callback: Callable[[dict | None, float], None]) -> "EyeTracker":
        self._callback = callback
        return self

    def clear_gaze_listener(self) -> "EyeTracker":
        self._callback = None
        return self

    def get_current_prediction(self) -> dict | None:
        return self._latest_gaze

    def get_latest_frame(self) -> np.ndarray | None:
        return self._latest_frame

    def get_latest_landmarks(self) -> list | None:
        return self._latest_landmarks

    def record_screen_position(self, x: float, y: float, event_type: str = "click") -> "EyeTracker":
        """Record a calibration point: maps current eye features to screen position."""
        if self._paused or self._latest_eye_features is None:
            return self
        left, right = self._latest_eye_features
        for reg in self._regs:
            reg.add_data(left, right, [x, y], event_type)
        return self

    def save_calibration(self, path: Path) -> None:
        """Persist click-based calibration data to disk."""
        reg = self._regs[0]
        if reg.eye_features_clicks.length == 0:
            return
        data = {
            "screen_x_clicks": reg.screen_x_clicks.data,
            "screen_y_clicks": reg.screen_y_clicks.data,
            "eye_features_clicks": reg.eye_features_clicks.data,
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data), encoding="utf-8")
        except OSError as exc:
            logger.warning("Failed to save calibration to %s: %s", path, exc)

    def load_calibration(self, path: Path) -> bool:
        """Load previously saved calibration data. Returns True on success."""
        if not path.is_file():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            reg = self._regs[0]
            for item in data["screen_x_clicks"]:
                reg.screen_x_clicks.push(item)
            for item in data["screen_y_clicks"]:
                reg.screen_y_clicks.push(item)
            for item in data["eye_features_clicks"]:
                reg.eye_features_clicks.push(item)
            return True
        except (OSError, KeyError, json.JSONDecodeError, ValueError) as exc:
            logger.warning("Failed to load calibration from %s: %s", path, exc)
            return False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _loop(self):
        """Main prediction loop running in a background thread."""
        while self._running:
            if self._paused:
                time.sleep(0.01)
                continue

            if not self._cap or not self._cap.isOpened():
                time.sleep(0.01)
                continue

            ret, frame = self._cap.read()
            if not ret or frame is None:
                time.sleep(0.01)
                continue

            # On macOS, if camera permission was just granted the capture returns
            # black frames until the AVFoundation session is reopened. Track
            # consecutive empty frames and reopen after the threshold — this
            # handles the async permission dialog (user clicks OK after begin()).
            if platform.system() == "Darwin" and not frame.any():
                self._empty_frame_count += 1
                if self._empty_frame_count >= 30:
                    logger.info("Camera returning empty frames, reopening (permission granted?)")
                    self._cap.release()
                    time.sleep(0.5)
                    new_cap = self._open_capture(self._camera_index)
                    if new_cap:
                        self._cap = new_cap
                    self._empty_frame_count = 0
                time.sleep(0.01)
                continue
            self._empty_frame_count = 0

            self._latest_frame = frame

            # Run face tracker
            result = self._tracker.get_eye_patches(frame)
            if result is None:
                self._latest_eye_features = None
                time.sleep(self.params.data_timestep / 1000.0)
                continue

            left, right, landmarks = result
            self._latest_landmarks = landmarks

            # Blink detection
            self._blink_detector.detect_blink(left, right, blink_detection_on=True)

            self._latest_eye_features = (left, right)

            # Gaze prediction
            gaze = self._get_prediction(left, right)
            elapsed = time.time() - self._clock_start

            if gaze:
                # Sliding-window smoothing: average gaze over the last N predictions
                # to reduce jitter without introducing significant latency.
                if self._smoothing.window_size != self.smoothing_window_size:
                    self._smoothing = DataWindow(self.smoothing_window_size)
                self._smoothing.push(gaze)
                sx = sum(self._smoothing.get(i)["x"] for i in range(self._smoothing.length)) / self._smoothing.length
                sy = sum(self._smoothing.get(i)["y"] for i in range(self._smoothing.length)) / self._smoothing.length
                gaze = bound({"x": sx, "y": sy}, self._screen_width, self._screen_height)

            self._latest_gaze = gaze

            if self._callback:
                self._callback(gaze, elapsed)

            time.sleep(self.params.data_timestep / 1000.0)

    def _get_prediction(self, left: Eye, right: Eye) -> dict | None:
        if not self._regs:
            return None
        return self._regs[0].predict(left, right)
