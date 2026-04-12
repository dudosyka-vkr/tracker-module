"""Tests for compute_roi_metrics and revisit helpers."""

import math

from eyetracker.core.roi import _count_revisits, compute_roi_metrics, compute_tge, fixation_aoi_sequence

# Unit square AOI polygon (normalized)
_SQUARE = [
    {"x": 0.0, "y": 0.0},
    {"x": 1.0, "y": 0.0},
    {"x": 1.0, "y": 1.0},
    {"x": 0.0, "y": 1.0},
]

# Small top-left AOI
_TOP_LEFT = [
    {"x": 0.0, "y": 0.0},
    {"x": 0.4, "y": 0.0},
    {"x": 0.4, "y": 0.4},
    {"x": 0.0, "y": 0.4},
]

# Small bottom-right AOI (no overlap with _TOP_LEFT)
_BOTTOM_RIGHT = [
    {"x": 0.6, "y": 0.6},
    {"x": 1.0, "y": 0.6},
    {"x": 1.0, "y": 1.0},
    {"x": 0.6, "y": 1.0},
]


def _fix(cx: float, cy: float, start_ms: int, is_first: bool = False) -> dict:
    return {
        "center": {"x": cx, "y": cy},
        "start_ms": start_ms,
        "is_first": is_first,
    }


# ---------------------------------------------------------------------------
# aoi_first_fixation
# ---------------------------------------------------------------------------


def test_aoi_first_fixation_single_hit():
    aoi = [{"name": "A", "color": "#ffffff", "first_fixation": False, "points": _SQUARE}]
    fixations = [_fix(0.5, 0.5, 100, is_first=True)]
    result = compute_roi_metrics(aoi, fixations)
    assert result[0]["aoi_first_fixation"] == 100


def test_aoi_first_fixation_no_hit():
    aoi = [{"name": "A", "color": "#ffffff", "first_fixation": False, "points": _TOP_LEFT}]
    # Fixation is outside _TOP_LEFT (bottom-right region)
    fixations = [_fix(0.8, 0.8, 200, is_first=True)]
    result = compute_roi_metrics(aoi, fixations)
    assert result[0]["aoi_first_fixation"] is None


def test_aoi_first_fixation_multiple_fixations_returns_earliest():
    aoi = [{"name": "A", "color": "#ffffff", "first_fixation": False, "points": _TOP_LEFT}]
    fixations = [
        _fix(0.8, 0.8, 50, is_first=True),   # outside AOI
        _fix(0.2, 0.2, 150),                  # inside AOI — first hit
        _fix(0.1, 0.1, 300),                  # inside AOI — later hit
    ]
    result = compute_roi_metrics(aoi, fixations)
    assert result[0]["aoi_first_fixation"] == 150


def test_aoi_first_fixation_independent_per_aoi():
    aoi = [
        {"name": "TL", "color": "#ff0000", "first_fixation": False, "points": _TOP_LEFT},
        {"name": "BR", "color": "#00ff00", "first_fixation": False, "points": _BOTTOM_RIGHT},
    ]
    fixations = [
        _fix(0.8, 0.8, 100, is_first=True),   # hits BR, not TL
        _fix(0.2, 0.2, 200),                   # hits TL, not BR
    ]
    result = compute_roi_metrics(aoi, fixations)
    tl = next(r for r in result if r["name"] == "TL")
    br = next(r for r in result if r["name"] == "BR")
    assert tl["aoi_first_fixation"] == 200
    assert br["aoi_first_fixation"] == 100


def test_aoi_first_fixation_no_fixations():
    aoi = [{"name": "A", "color": "#ffffff", "first_fixation": False, "points": _SQUARE}]
    result = compute_roi_metrics(aoi, [])
    assert result[0]["aoi_first_fixation"] is None


def test_aoi_first_fixation_with_first_fixation_required():
    """aoi_first_fixation is always the first fixation inside AOI, regardless of first_fixation_required."""
    aoi = [{"name": "A", "color": "#ffffff", "first_fixation": True, "points": _TOP_LEFT}]
    fixations = [
        _fix(0.8, 0.8, 50, is_first=True),   # outside — overall first, not in AOI
        _fix(0.2, 0.2, 150),                  # inside AOI
    ]
    result = compute_roi_metrics(aoi, fixations)
    # hit=False because first overall fixation is NOT in AOI
    assert result[0]["hit"] is False
    # aoi_first_fixation is still 150 (first fixation that lands in AOI)
    assert result[0]["aoi_first_fixation"] == 150


def test_aoi_first_fixation_empty_aoi_list():
    assert compute_roi_metrics([], [_fix(0.5, 0.5, 100, is_first=True)]) == []


# ---------------------------------------------------------------------------
# _count_revisits — unit tests on the label sequence directly
# ---------------------------------------------------------------------------


def test_count_revisits_example_from_spec():
    # AOI3 -> AOI1 -> out -> AOI1 -> AOI2 -> AOI2 -> AOI3
    seq = ["AOI3", "AOI1", None, "AOI1", "AOI2", "AOI2", "AOI3"]
    r = _count_revisits(seq)
    assert r["AOI3"] == 1
    assert r["AOI1"] == 1
    assert r["AOI2"] == 0


def test_count_revisits_no_revisits():
    seq = ["A", "B", "C"]
    r = _count_revisits(seq)
    assert r == {"A": 0, "B": 0, "C": 0}


def test_count_revisits_all_same_aoi():
    # Consecutive runs of same AOI count as one visit
    seq = ["A", "A", "A"]
    r = _count_revisits(seq)
    assert r == {"A": 0}


def test_count_revisits_multiple_revisits():
    seq = ["A", "B", "A", "B", "A"]
    r = _count_revisits(seq)
    assert r["A"] == 2
    assert r["B"] == 1


def test_count_revisits_out_between_same():
    # Leaving via "out" and returning counts as a revisit
    seq = ["A", None, "A"]
    r = _count_revisits(seq)
    assert r["A"] == 1


def test_count_revisits_empty_sequence():
    assert _count_revisits([]) == {}


def test_count_revisits_only_out():
    assert _count_revisits([None, None, None]) == {}


# ---------------------------------------------------------------------------
# revisits field in compute_roi_metrics
# ---------------------------------------------------------------------------


def test_revisits_field_present():
    aoi = [{"name": "A", "color": "#fff", "first_fixation": False, "points": _TOP_LEFT}]
    result = compute_roi_metrics(aoi, [])
    assert "revisits" in result[0]
    assert result[0]["revisits"] == 0


# ---------------------------------------------------------------------------
# fixation_aoi_sequence
# ---------------------------------------------------------------------------


def test_fixation_aoi_sequence_labels():
    aoi = [
        {"name": "TL", "color": "#f00", "first_fixation": False, "points": _TOP_LEFT},
        {"name": "BR", "color": "#0f0", "first_fixation": False, "points": _BOTTOM_RIGHT},
    ]
    fixations = [
        _fix(0.8, 0.8, 10, is_first=True),  # BR
        _fix(0.2, 0.2, 20),                  # TL
        _fix(0.5, 0.5, 30),                  # out
        _fix(0.2, 0.2, 40),                  # TL
    ]
    seq = fixation_aoi_sequence(aoi, fixations)
    assert seq == ["BR", "TL", None, "TL"]


def test_fixation_aoi_sequence_empty_fixations():
    aoi = [{"name": "A", "color": "#fff", "first_fixation": False, "points": _SQUARE}]
    assert fixation_aoi_sequence(aoi, []) == []


def test_fixation_aoi_sequence_empty_aoi():
    assert fixation_aoi_sequence([], [_fix(0.5, 0.5, 10)]) == [None]


def test_revisits_via_compute_roi_metrics():
    aoi = [
        {"name": "TL", "color": "#f00", "first_fixation": False, "points": _TOP_LEFT},
        {"name": "BR", "color": "#0f0", "first_fixation": False, "points": _BOTTOM_RIGHT},
    ]
    # sequence: BR -> TL -> out -> TL -> BR -> BR -> BR (matches spec example structure)
    fixations = [
        _fix(0.8, 0.8, 10, is_first=True),   # BR
        _fix(0.2, 0.2, 20),                   # TL
        _fix(0.5, 0.5, 30),                   # out (between the two AOIs)
        _fix(0.2, 0.2, 40),                   # TL (revisit)
        _fix(0.8, 0.8, 50),                   # BR (revisit)
        _fix(0.8, 0.8, 60),                   # BR (same visit)
        _fix(0.8, 0.8, 70),                   # BR (same visit)
    ]
    result = compute_roi_metrics(aoi, fixations)
    tl = next(r for r in result if r["name"] == "TL")
    br = next(r for r in result if r["name"] == "BR")
    assert tl["revisits"] == 1
    assert br["revisits"] == 1


# ---------------------------------------------------------------------------
# compute_tge
# ---------------------------------------------------------------------------


def test_tge_empty_sequence():
    assert compute_tge([]) is None


def test_tge_only_none():
    assert compute_tge([None, None, None]) is None


def test_tge_single_aoi_no_transitions():
    # Only one AOI visited — no transitions, entropy = 0
    assert compute_tge(["A", "A", "A"]) == 0.0


def test_tge_two_aois_deterministic():
    # Perfect alternation A→B→A→B: p(A→B)=1, p(B→A)=1 → per-zone entropy=0
    seq = ["A", "B", "A", "B"]
    tge = compute_tge(seq)
    assert tge == 0.0


def test_tge_mixed_transitions():
    # A→None→A creates a self-transition in the bridged sequence; A→B is also present
    # compressed: ["A", None, "A", "B"]
    # transitions (bridging None): A→A:1, A→B:1 → H(A) = 1 bit; B has no outgoing → H(B)=0
    # dwell: A=2, B=1 → p_A=2/3, p_B=1/3
    # TGE = (2/3)*1 + (1/3)*0 = 2/3
    seq = ["A", None, "A", "B"]
    tge = compute_tge(seq)
    expected = 2 / 3
    assert tge is not None
    assert abs(tge - expected) < 1e-9


def test_tge_ignores_none_gaps():
    # None gaps should not break transitions but bridge them
    seq = ["A", None, "B", None, "A"]
    tge_with_none = compute_tge(seq)
    tge_without = compute_tge(["A", "B", "A"])
    # dwell differs (None entries ignored in raw count), but transitions same
    # Both should yield 0.0 (perfect A↔B alternation)
    assert tge_with_none == 0.0
    assert tge_without == 0.0


def test_tge_nonnegative():
    seq = ["A", "B", "C", "A", "C", "B", "A"]
    tge = compute_tge(seq)
    assert tge is not None
    assert tge >= 0.0


def test_tge_higher_for_random_transitions():
    # Ordered path A→B→C has lower entropy than random visits
    ordered = ["A", "B", "C", "A", "B", "C"]
    random_seq = ["A", "C", "B", "A", "B", "C", "A", "C"]
    tge_ordered = compute_tge(ordered)
    tge_random = compute_tge(random_seq)
    assert tge_ordered is not None
    assert tge_random is not None
    assert tge_random > tge_ordered
