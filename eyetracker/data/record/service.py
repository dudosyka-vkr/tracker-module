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


@dataclass
class RecordListResult:
    """Paginated list of record summaries."""

    items: list[RecordSummary]
    page: int
    page_size: int
    total: int


@dataclass
class RecordQuery:
    """Query parameters for listing records.

    Compatible with backend GET /records endpoint.
    """

    test_id: str | None = None
    user_login: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    page: int = 1
    page_size: int = 20


class RecordService(ABC):
    """Abstract interface for record persistence."""

    @abstractmethod
    def save(self, record: Record) -> None: ...

    @abstractmethod
    def query(self, params: RecordQuery) -> RecordListResult: ...

    @abstractmethod
    def load(self, record_id: str) -> Record | None: ...
