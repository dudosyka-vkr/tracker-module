"""Persistent draft cache for test create/edit forms."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_PATH = Path.home() / ".eyetracker" / "draft.json"


@dataclass
class DraftData:
    """Serializable draft state."""

    draft_type: str  # "create" | "edit"
    test_id: str | None  # only for "edit"
    name: str
    cover_path: str | None
    image_paths: list[str]


class DraftCache:
    """Read/write draft cache from a JSON file.

    Default location: ~/.eyetracker/draft.json
    """

    def __init__(self, path: Path | None = None):
        self._path = path or _DEFAULT_PATH

    def save(self, draft: DraftData) -> None:
        try:
            os.makedirs(self._path.parent, exist_ok=True)
            self._path.write_text(
                json.dumps(asdict(draft), indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("Failed to save draft to %s: %s", self._path, exc)

    def load(self) -> DraftData | None:
        if not self._path.is_file():
            return None
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return None
            return DraftData(
                draft_type=data.get("draft_type", "create"),
                test_id=data.get("test_id"),
                name=data.get("name", ""),
                cover_path=data.get("cover_path"),
                image_paths=data.get("image_paths", []),
            )
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load draft from %s: %s", self._path, exc)
            return None

    def clear(self) -> None:
        try:
            if self._path.is_file():
                self._path.unlink()
        except OSError as exc:
            logger.warning("Failed to clear draft at %s: %s", self._path, exc)

    def exists(self) -> bool:
        return self._path.is_file()
