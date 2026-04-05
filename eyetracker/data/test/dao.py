"""Abstract test data model and DAO interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TestData:
    """Metadata for a single test."""

    id: str
    name: str
    cover_filename: str
    image_filenames: list[str]
    image_regions: dict = field(default_factory=dict)


class TestDao(ABC):
    """Abstract interface for test persistence.

    Implementations may store tests locally (LocalTestDao) or via remote API.
    """

    @abstractmethod
    def create(self, name: str, cover_src: Path, image_srcs: list[Path]) -> TestData:
        """Create a test: copy files to storage, persist metadata."""

    @abstractmethod
    def load_all(self) -> list[TestData]:
        """Load all tests."""

    @abstractmethod
    def load(self, test_id: str) -> TestData | None:
        """Load a test by ID."""

    @abstractmethod
    def update(self, test_id: str, name: str, cover_src: Path, image_srcs: list[Path]) -> TestData:
        """Update a test: replace files in storage, update metadata."""

    @abstractmethod
    def delete(self, test_id: str) -> None:
        """Delete a test and its files."""

    @abstractmethod
    def get_cover_path(self, test: TestData) -> Path:
        """Return absolute path to the test cover image."""

    @abstractmethod
    def get_image_path(self, test: TestData, filename: str) -> Path:
        """Return absolute path to a test image by filename."""

    @abstractmethod
    def save_regions(self, test_id: str, regions: dict[str, list[dict]]) -> None:
        """Persist only the image_regions field for an existing test."""
