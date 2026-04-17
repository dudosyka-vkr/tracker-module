"""Tests for RecordService."""

from eyetracker.data.record import (
    LocalRecordService,
    Record,
    RecordMetrics,
    RecordQuery,
)


def _make_record(
    record_id: str = "r1",
    test_id: str = "t1",
    user_login: str = "local",
    started_at: str = "2025-01-01T00:00:00Z",
    created_at: str = "2025-01-01T00:00:10Z",
) -> Record:
    return Record(
        id=record_id,
        test_id=test_id,
        user_login=user_login,
        started_at=started_at,
        finished_at="2025-01-01T00:00:10Z",
        duration_ms=10000,
        metrics=RecordMetrics(
            gaze_groups=[{"x": 0.5, "y": 0.5, "count": 10}],
        ),
        created_at=created_at,
    )


def test_save_and_load_roundtrip(tmp_path):
    svc = LocalRecordService(base_dir=tmp_path)
    record = _make_record()
    svc.save(record)

    loaded = svc.load("r1")
    assert loaded is not None
    assert loaded.id == "r1"
    assert loaded.test_id == "t1"
    assert loaded.user_login == "local"
    assert loaded.started_at == "2025-01-01T00:00:00Z"
    assert loaded.finished_at == "2025-01-01T00:00:10Z"
    assert loaded.duration_ms == 10000
    assert loaded.metrics.gaze_groups == [{"x": 0.5, "y": 0.5, "count": 10}]


def test_query_returns_summaries(tmp_path):
    svc = LocalRecordService(base_dir=tmp_path)
    svc.save(_make_record("r1", "t1"))

    result = svc.query(RecordQuery(test_id="t1"))
    assert len(result.items) == 1
    summary = result.items[0]
    assert summary.id == "r1"
    assert summary.user_login == "local"


def test_query_filters_by_test_id(tmp_path):
    svc = LocalRecordService(base_dir=tmp_path)
    svc.save(_make_record("r1", "t1"))
    svc.save(_make_record("r2", "t2"))
    svc.save(_make_record("r3", "t1"))

    result = svc.query(RecordQuery(test_id="t1"))
    ids = sorted(r.id for r in result.items)
    assert ids == ["r1", "r3"]
    assert result.total == 2


def test_query_filters_by_user_login(tmp_path):
    svc = LocalRecordService(base_dir=tmp_path)
    svc.save(_make_record("r1", "t1", user_login="alice"))
    svc.save(_make_record("r2", "t1", user_login="bob"))

    result = svc.query(RecordQuery(user_login="alice"))
    assert len(result.items) == 1
    assert result.items[0].id == "r1"


def test_query_filters_by_date_range(tmp_path):
    svc = LocalRecordService(base_dir=tmp_path)
    svc.save(_make_record("r1", "t1", started_at="2025-01-01T00:00:00Z"))
    svc.save(_make_record("r2", "t1", started_at="2025-01-15T00:00:00Z"))
    svc.save(_make_record("r3", "t1", started_at="2025-02-01T00:00:00Z"))

    result = svc.query(RecordQuery(
        date_from="2025-01-10T00:00:00Z",
        date_to="2025-01-20T00:00:00Z",
    ))
    assert len(result.items) == 1
    assert result.items[0].id == "r2"


def test_query_pagination(tmp_path):
    svc = LocalRecordService(base_dir=tmp_path)
    for i in range(5):
        svc.save(_make_record(f"r{i}", "t1", created_at=f"2025-01-0{i + 1}T00:00:00Z"))

    page1 = svc.query(RecordQuery(page=1, page_size=2))
    assert len(page1.items) == 2
    assert page1.total == 5
    assert page1.page == 1

    page3 = svc.query(RecordQuery(page=3, page_size=2))
    assert len(page3.items) == 1
    assert page3.total == 5


def test_load_nonexistent(tmp_path):
    svc = LocalRecordService(base_dir=tmp_path)
    assert svc.load("nonexistent") is None


def test_query_empty_dir(tmp_path):
    svc = LocalRecordService(base_dir=tmp_path)
    result = svc.query(RecordQuery(test_id="t1"))
    assert result.items == []
    assert result.total == 0
