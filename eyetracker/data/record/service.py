"""Abstract record data model and service interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class RecordItemMetrics:
    """Gaze metrics for a single image."""

    gaze_groups: list[dict]
    fixations: list[dict] = field(default_factory=list)
    first_fixation_time_ms: int | None = None
    saccades: list[dict] = field(default_factory=list)
    roi_metrics: list[dict] = field(default_factory=list)
    # roi_metrics entries: {"name": str, "color": str, "hit": bool, "first_fixation_required": bool}


@dataclass
class RecordItem:
    """One image's data within a record."""

    image_filename: str
    image_index: int
    metrics: RecordItemMetrics


@dataclass
class Record:
    """A completed test run."""

    id: str
    test_id: str
    user_login: str
    started_at: str
    finished_at: str
    duration_ms: int
    items: list[RecordItem]
    created_at: str


@dataclass
class RecordSummary:
    """Record metadata without items (for list views)."""

    id: str
    test_id: str
    user_login: str
    started_at: str
    finished_at: str
    duration_ms: int
    created_at: str
    roi_hits: list[dict] = field(default_factory=list)
    # roi_hits entries: {"name": str, "hit": bool}


@dataclass
class RecordListResult:
    """Paginated list of record summaries."""

    items: list[RecordSummary]
    page: int
    page_size: int
    total: int


@dataclass
class RoiStat:
    """Aggregated hit statistics for a single ROI across all records of a test."""

    name: str
    color: str
    hits: int
    total: int
    first_fixation_required: bool


@dataclass
class RecordQuery:
    """Query parameters for listing records.

    Compatible with backend GET /records endpoint.
    """

    test_id: str | None = None
    user_login: str | None = None
    user_login_contains: str | None = None
    date_from: str | None = None  # ISO-8601 string
    date_to: str | None = None    # ISO-8601 string
    roi_hits: dict[str, bool] | None = None  # {roi_name: True=hit, False=not hit}
    page: int = 1
    page_size: int = 20


class RecordService(ABC):
    """Abstract interface for record persistence."""

    @abstractmethod
    def save(self, record: Record) -> None: ...

    @abstractmethod
    def save_unauthorized(self, record: Record, token: str, login: str) -> None:
        """Save a record without authentication using an 8-digit test token."""
        ...

    @abstractmethod
    def query(self, params: RecordQuery) -> RecordListResult: ...

    @abstractmethod
    def load(self, record_id: str) -> Record | None: ...

    @abstractmethod
    def suggest_users(self, params: RecordQuery) -> list[str]:
        """Return sorted unique user logins matching params (user fields ignored)."""
        ...

    @abstractmethod
    def get_roi_stats(self, test_id: str) -> list[RoiStat]:
        """Return aggregated ROI hit statistics for all records of the given test."""
        ...

    @abstractmethod
    def is_roi_sync_needed(self, test_id: str, image_regions: dict) -> bool:
        """Return True if any record item for the test has stale ROI metrics.

        ``image_regions`` is the test's current {filename: [roi, …]} mapping.
        Remote implementations may ignore it and query the server instead.
        """
        ...
