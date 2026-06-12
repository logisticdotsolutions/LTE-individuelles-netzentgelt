from datetime import datetime, timezone
from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ukl_vens_mapping_module as module


def row(vens, start=None, end=None, priority=100):
    return {
        "performing_ru": "LTE DE - LTE Germany GmbH",
        "user_vens": vens,
        "valid_from": start,
        "valid_to": end,
        "priority": priority,
    }


def utc(text):
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


def test_resolver_uses_time_window_and_end_is_exclusive():
    mappings = (
        row("VENS-OLD", end=utc("2026-06-10T00:00:00")),
        row("VENS-NEW", start=utc("2026-06-10T00:00:00")),
    )
    assert module.resolve_user_vens(
        performing_ru="LTE DE - LTE Germany GmbH",
        at_utc="2026-06-09T23:59:59Z",
        mapping_rows=mappings,
    ) == "VENS-OLD"
    assert module.resolve_user_vens(
        performing_ru="LTE DE - LTE Germany GmbH",
        at_utc="2026-06-10T00:00:00Z",
        mapping_rows=mappings,
    ) == "VENS-NEW"


def test_resolver_uses_lowest_priority_number():
    mappings = (row("VENS-LOW", priority=200), row("VENS-HIGH", priority=1))
    assert module.resolve_user_vens(
        performing_ru="LTE DE - LTE Germany GmbH",
        at_utc="2026-06-09T12:00:00Z",
        mapping_rows=mappings,
    ) == "VENS-HIGH"


def test_resolver_rejects_equal_priority_conflict():
    mappings = (row("VENS-A", priority=1), row("VENS-B", priority=1))
    with pytest.raises(module.VEnsMappingConflict):
        module.resolve_user_vens(
            performing_ru="LTE DE - LTE Germany GmbH",
            at_utc="2026-06-09T12:00:00Z",
            mapping_rows=mappings,
        )


def test_apply_mapping_overwrites_static_loco_fallback(monkeypatch):
    monkeypatch.setattr(module, "load_mapping", lambda path: (row("VENS-MAPPED"),))
    result = module.apply_vens_mapping(
        [{
            "performing_ru": "LTE DE - LTE Germany GmbH",
            "usage_start": "2026-06-09T12:00:00Z",
            "user_vens": "STATIC-LOCO-FALLBACK",
        }],
        timestamp_keys=("usage_start",),
        mapping_path=Path("dummy.csv"),
    )
    assert result[0]["user_vens"] == "VENS-MAPPED"
