"""Application settings persistence via JSON file."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_PATH = Path.home() / ".eyetracker" / "settings.json"


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
