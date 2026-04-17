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
    image_filename: str
    aoi: list[dict] = field(default_factory=list)
    author: str = ""


class TestDao(ABC):
    """Abstract interface for test persistence.

    Implementations may store tests locally (LocalTestDao) or via remote API.
    """

    @abstractmethod
    def create(self, name: str, image_src: Path) -> TestData:
        """Create a test: copy image to storage, persist metadata."""

    @abstractmethod
    def load_all(self) -> list[TestData]:
        """Load all tests."""

    @abstractmethod
    def load(self, test_id: str) -> TestData | None:
        """Load a test by ID."""

    @abstractmethod
    def delete(self, test_id: str) -> None:
        """Delete a test and its files."""

    @abstractmethod
    def get_image_path(self, test: TestData) -> Path:
        """Return absolute path to the test image."""

    @abstractmethod
    def update_name(self, test_id: str, name: str) -> TestData:
        """Update only the name of an existing test."""

    @abstractmethod
    def save_aoi(self, test_id: str, aoi: list[dict]) -> None:
        """Persist the AOI (areas of interest) for an existing test."""

    @abstractmethod
    def load_by_token(self, code: str) -> TestData | None:
        """Load a test by its 8-digit access code (no auth required)."""

    @abstractmethod
    def get_token(self, test_id: str) -> str:
        """Generate (or return existing) 8-digit access code for the test."""

    @abstractmethod
    def sync_aoi_metrics(self, test_id: str, record_service: object) -> None:
        """Recompute AOI metrics for every record that belongs to this test."""
