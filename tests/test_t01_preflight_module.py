from datetime import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import t01_preflight_module as module


def row(**overrides):
    value = {
        "locomotive_no": "91801234567-8",
        "user_vens": "1900100300001",
        "departure_ts": datetime(2026, 6, 9, 8, 0),
        "departure_location": "8000261",
        "arrival_ts": datetime(2026, 6, 9, 10, 0),
        "arrival_location": "8000207",
        "distance_km": 120.0,
        "trailer_weight_t": 900.0,
        "order_criterion": "Güterverkehr",
        "usage_type": "SE",
        "max_speed_kmh": 120,
        "is_multiple_unit": False,
    }
    value.update(overrides)
    return value


def codes(rows):
    return {issue.code for issue in module.validate_t01_rows(rows)}


def test_valid_t01_row_passes():
    assert module.validate_t01_rows([row()]) == []


def test_or_forbids_speed():
    assert "T01_OR_SPEED_MUST_BE_EMPTY" in codes([row(usage_type="OR")])


def test_non_or_requires_speed():
    assert "T01_MAX_SPEED_REQUIRED" in codes([row(max_speed_kmh=None)])


def test_lln_requires_zero_trailer_weight():
    assert "T01_LLN_TRAILER_WEIGHT_MUST_BE_ZERO" in codes([row(usage_type="LLN")])


def test_multiple_unit_rules_are_enforced():
    result = codes([row(is_multiple_unit=True)])
    assert "T01_MULTIPLE_UNIT_FREIGHT_FORBIDDEN" in result
    assert "T01_MULTIPLE_UNIT_TRAILER_WEIGHT_MUST_BE_ZERO" in result


def test_overlaps_are_blocked_per_locomotive():
    result = codes([
        row(),
        row(departure_ts=datetime(2026, 6, 9, 9, 0), arrival_ts=datetime(2026, 6, 9, 11, 0)),
    ])
    assert "T01_OVERLAP" in result
