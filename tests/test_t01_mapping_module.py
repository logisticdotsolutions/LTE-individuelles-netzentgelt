from datetime import datetime, timezone
from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import t01_mapping_module as module


def utc(text):
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


def test_classification_prefers_lowest_priority_number():
    mappings = (
        {"source_field": "transport_type", "source_value": "Train", "bestellkriterium": "Güterverkehr", "verwendungsart": "SE", "priority": 100},
        {"source_field": "movement_type", "source_value": "Light", "bestellkriterium": "Güterverkehr", "verwendungsart": "LLA", "priority": 1},
    )
    assert module.resolve_classification({"transport_type": "Train", "movement_type": "Light"}, mappings) == ("Güterverkehr", "LLA")


def test_classification_rejects_equal_priority_conflict():
    mappings = (
        {"source_field": "*", "source_value": "*", "bestellkriterium": "Güterverkehr", "verwendungsart": "SE", "priority": 1},
        {"source_field": "*", "source_value": "*", "bestellkriterium": "Güterverkehr", "verwendungsart": "LLA", "priority": 1},
    )
    with pytest.raises(module.T01MappingConflict):
        module.resolve_classification({}, mappings)


def test_locomotive_characteristics_use_time_window():
    mappings = (
        {"loco_no": "91801234567-8", "max_speed_kmh": "120", "is_multiple_unit": False, "valid_from": None, "valid_to": utc("2026-06-10T00:00:00"), "priority": 100},
        {"loco_no": "91801234567-8", "max_speed_kmh": "140", "is_multiple_unit": False, "valid_from": utc("2026-06-10T00:00:00"), "valid_to": None, "priority": 100},
    )
    old = module.resolve_locomotive_characteristics(loco_no="91801234567-8", at_utc="2026-06-09T23:59:59Z", mappings=mappings)
    new = module.resolve_locomotive_characteristics(loco_no="91801234567-8", at_utc="2026-06-10T00:00:00Z", mappings=mappings)
    assert old["max_speed_kmh"] == "120"
    assert new["max_speed_kmh"] == "140"
