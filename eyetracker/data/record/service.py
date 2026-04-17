"""Abstract record data model and service interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class RecordMetrics:
    """Gaze metrics for a test record."""

    gaze_groups: list[dict]
    fixations: list[dict] = field(default_factory=list)
    first_fixation_time_ms: int | None = None
    saccades: list[dict] = field(default_factory=list)
    roi_metrics: list[dict] = field(default_factory=list)
    # roi_metrics entries: {"name": str, "color": str, "hit": bool, "first_fixation_required": bool, "aoi_first_fixation": int | None, "revisits": int}
    aoi_sequence: list = field(default_factory=list)
    # aoi_sequence: per-fixation AOI label (str name or null); same order as fixations
    tge: float | None = None
    # tge: Transition Gaze Entropy — conditional entropy of AOI-to-AOI transitions


@dataclass
class Record:
    """A completed test run."""

    id: str
    test_id: str
    user_login: str
    started_at: str
    finished_at: str
    duration_ms: int
    metrics: RecordMetrics
    created_at: str


@dataclass
class RecordSummary:
    """Record metadata without metrics (for list views)."""

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
    first_fixation_histogram: list = field(default_factory=list)
    # first_fixation_histogram: list of {"binStartMs": int, "count": int}, 500 ms bins


@dataclass
class AoiStatsResult:
    """Full AOI stats response: per-AOI stats + session-level TGE histogram."""

    aois: list[RoiStat] = field(default_factory=list)
    tge_histogram: list = field(default_factory=list)
    # tge_histogram: list of {"binStart": float, "count": int}, bin width = 0.1


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
    def get_aoi_stats(self, test_id: str) -> AoiStatsResult:
        """Return aggregated AOI hit statistics + TGE histogram for the given test."""
        ...

    @abstractmethod
    def is_aoi_sync_needed(self, test_id: str, aoi: list[dict]) -> bool:
        """Return True if any record for the test has stale AOI metrics.

        ``aoi`` is the test's current AOI list.
        Remote implementations may ignore it and query the server instead.
        """
        ...
