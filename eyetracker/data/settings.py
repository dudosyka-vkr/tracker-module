"""Application settings persistence via JSON file."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_PATH = Path.home() / ".eyetracker" / "settings.json"

_DEFAULT_SERVER_URL: str | None = "https://vkr.dudosyka.ru"


class Settings:
    """Read/write application settings from a JSON file.

    Default location: ~/.eyetracker/settings.json
    """

    def __init__(self, path: Path | None = None):
        self._path = path or _DEFAULT_PATH
        self._data: dict = {}
        self._load()

    @property
    def tracking_display_name(self) -> str | None:
        """Monitor name for tracking. None means primary monitor."""
        return self._data.get("tracking_display_name")

    @tracking_display_name.setter
    def tracking_display_name(self, value: str | None) -> None:
        if value is None:
            self._data.pop("tracking_display_name", None)
        else:
            self._data["tracking_display_name"] = value
        self._save()

    @property
    def auth_token(self) -> str | None:
        """Stored JWT token. None means logged out."""
        return self._data.get("auth_token")

    @auth_token.setter
    def auth_token(self, value: str | None) -> None:
        if value is None:
            self._data.pop("auth_token", None)
        else:
            self._data["auth_token"] = value
        self._save()

    @property
    def skip_calibration(self) -> bool:
        """Whether to skip the calibration dot-clicking phase."""
        return self._data.get("skip_calibration", False)

    @skip_calibration.setter
    def skip_calibration(self, value: bool) -> None:
        self._data["skip_calibration"] = value
        self._save()

    @property
    def show_gaze_marker(self) -> bool:
        """Whether to draw the gaze dot on screen during a test run."""
        return self._data.get("show_gaze_marker", False)

    @show_gaze_marker.setter
    def show_gaze_marker(self, value: bool) -> None:
        self._data["show_gaze_marker"] = value
        self._save()

    @property
    def fixation_enabled(self) -> bool:
        """Whether fixation detection is active during test runs."""
        return self._data.get("fixation_enabled", True)

    @fixation_enabled.setter
    def fixation_enabled(self, value: bool) -> None:
        self._data["fixation_enabled"] = value
        self._save()

    @property
    def fixation_radius_threshold_k(self) -> float:
        """Fixation radius threshold in screen pixels."""
        return float(self._data.get("fixation_radius_threshold_k", 80.0))

    @fixation_radius_threshold_k.setter
    def fixation_radius_threshold_k(self, value: float) -> None:
        self._data["fixation_radius_threshold_k"] = value
        self._save()

    @property
    def fixation_window_size_samples(self) -> int:
        """Number of recent gaze points kept in the fixation detection window."""
        return int(self._data.get("fixation_window_size_samples", 10))

    @fixation_window_size_samples.setter
    def fixation_window_size_samples(self, value: int) -> None:
        self._data["fixation_window_size_samples"] = value
        self._save()

    @property
    def image_display_duration_ms(self) -> int:
        """How long each test image is shown, in milliseconds."""
        return int(self._data.get("image_display_duration_ms", 5000))

    @image_display_duration_ms.setter
    def image_display_duration_ms(self, value: int) -> None:
        self._data["image_display_duration_ms"] = value
        self._save()

    @property
    def tracking_timestep_ms(self) -> int:
        """Gaze pipeline loop interval in milliseconds (controls sampling rate)."""
        return int(self._data.get("tracking_timestep_ms", 50))

    @tracking_timestep_ms.setter
    def tracking_timestep_ms(self, value: int) -> None:
        self._data["tracking_timestep_ms"] = value
        self._save()

    @property
    def current_username(self) -> str:
        """Username of the currently logged-in user."""
        return self._data.get("current_username", "")

    @current_username.setter
    def current_username(self, value: str) -> None:
        if value:
            self._data["current_username"] = value
        else:
            self._data.pop("current_username", None)
        self._save()

    @property
    def user_role(self) -> str | None:
        """Role of the currently logged-in user (USER / ADMIN / SUPER_ADMIN). None when logged out."""
        return self._data.get("user_role")

    @user_role.setter
    def user_role(self, value: str | None) -> None:
        if value is None:
            self._data.pop("user_role", None)
        else:
            self._data["user_role"] = value
        self._save()

    @property
    def server_url(self) -> str | None:
        """Backend server base URL. None means local-only mode."""
        return self._data.get("server_url", _DEFAULT_SERVER_URL)

    @server_url.setter
    def server_url(self, value: str | None) -> None:
        if value is None:
            self._data.pop("server_url", None)
        else:
            self._data["server_url"] = value
        self._save()

    @property
    def last_opened_test_id(self) -> str | None:
        """ID of the last opened test."""
        return self._data.get("last_opened_test_id")

    @last_opened_test_id.setter
    def last_opened_test_id(self, value: str | None) -> None:
        if value is None:
            self._data.pop("last_opened_test_id", None)
        else:
            self._data["last_opened_test_id"] = value
        self._save()

    def _load(self) -> None:
        if not self._path.is_file():
            return
        try:
            self._data = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(self._data, dict):
                self._data = {}
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load settings from %s: %s", self._path, exc)
            self._data = {}

    def _save(self) -> None:
        try:
            os.makedirs(self._path.parent, exist_ok=True)
            self._path.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("Failed to save settings to %s: %s", self._path, exc)
