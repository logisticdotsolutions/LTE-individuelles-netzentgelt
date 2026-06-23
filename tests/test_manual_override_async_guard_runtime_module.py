from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import manual_override_async_guard_runtime_module as guard


def test_is_rebuild_active_for_running_states(monkeypatch):
    for state in ["QUEUED", "RUNNING", "PENDING"]:
        monkeypatch.setattr(guard, "read_rebuild_status", lambda state=state: {"state": state})
        assert guard.is_rebuild_active() is True


def test_is_rebuild_active_false_for_current(monkeypatch):
    monkeypatch.setattr(guard, "read_rebuild_status", lambda: {"state": "CURRENT"})
    assert guard.is_rebuild_active() is False


def test_guarded_suggestion_avoids_original_during_rebuild(monkeypatch):
    monkeypatch.setattr(guard, "is_rebuild_active", lambda: True)

    def forbidden_original(*args, **kwargs):
        raise AssertionError("Original suggestion_for_case must not be called during rebuild")

    monkeypatch.setattr(guard, "_ORIGINAL_SUGGESTION_FOR_CASE", forbidden_original)

    suggestion = guard._suggestion_for_case_guarded(
        db_path=ROOT / "data" / "02_duckdb" / "netzentgelt.duckdb",
        override_type="SET_PERFORMING_RU",
        transport_number="T1",
        loco_no="193001",
        period_start_utc="2026-06-23T10:00:00",
        period_end_utc="2026-06-23T11:00:00",
        source_table="core_loco_timeline",
        source_row_id="42",
    )

    assert suggestion.suggestion_type == "MANUAL_REVIEW_DURING_REBUILD"
    assert suggestion.override_type == "SET_PERFORMING_RU"
    assert suggestion.transport_number == "T1"
    assert suggestion.loco_no == "193001"
    assert "Hintergrund-Neuberechnung" in suggestion.reason
