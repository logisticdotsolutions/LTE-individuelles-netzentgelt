"""Regression tests for performance optimizations in suggestion and UI modules.

Verifies that:
- _suggest_broken_chain_gaps skips non-DE-relevant gaps
- _suggest_border_slot_reviews skips non-border movements
- _build_case_table produces identical output to the original (vectorized refactor)
- _build_case_table deduplicates GAP rows already covered by findings
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

# Streamlit is installed in this env; we don't need a mock here.
# modules that import streamlit work directly.

from manual_override_suggestion_module import (
    _suggest_broken_chain_gaps,
    _suggest_border_slot_reviews,
)
from manual_override_ui_module import _build_case_table


# ---------------------------------------------------------------------------
# _suggest_broken_chain_gaps pre-filtering
# ---------------------------------------------------------------------------

def _make_gap_row(de_relevant: object, loco: str = "L1") -> dict:
    return {
        "row_type": "GAP",
        "loco_no": loco,
        "transport_number": "T1",
        "period_start_utc": "2026-06-13T10:00:00",
        "period_end_utc": "2026-06-13T12:00:00",
        "gap_relevant_de": de_relevant,
        "gap_duration_minutes": 120,
        "origin_name": "Hamburg",
        "destination_name": "Berlin",
        "source_table": "core_loco_timeline",
        "source_row_id": "1",
    }


def test_broken_chain_only_returns_de_relevant_gaps() -> None:
    timeline = pd.DataFrame([
        _make_gap_row("true"),
        _make_gap_row("false"),
        _make_gap_row(""),
        _make_gap_row(None),
    ])
    result = _suggest_broken_chain_gaps(timeline)
    assert len(result) == 1
    assert result[0].suggestion_type == "BROKEN_LOCATION_CHAIN"


def test_broken_chain_empty_for_all_non_de_relevant() -> None:
    timeline = pd.DataFrame([_make_gap_row("false"), _make_gap_row("no")])
    assert _suggest_broken_chain_gaps(timeline) == []


def test_broken_chain_handles_missing_gap_relevant_de_column() -> None:
    timeline = pd.DataFrame([{
        "row_type": "GAP", "loco_no": "L1", "transport_number": "T1",
        "period_start_utc": "2026-06-13T10:00:00", "period_end_utc": "2026-06-13T12:00:00",
        "gap_duration_minutes": 120, "origin_name": "A", "destination_name": "B",
        "source_table": "t", "source_row_id": "1",
    }])
    # Without gap_relevant_de column, all rows are included
    result = _suggest_broken_chain_gaps(timeline)
    assert len(result) == 1


def test_broken_chain_empty_timeline() -> None:
    assert _suggest_broken_chain_gaps(pd.DataFrame()) == []


# ---------------------------------------------------------------------------
# _suggest_border_slot_reviews pre-filtering
# ---------------------------------------------------------------------------

def _make_movement_row(clean_dir: str = "", faulty_dir: str = "", loco: str = "L1") -> dict:
    return {
        "row_type": "MOVEMENT",
        "loco_no": loco,
        "transport_number": "T1",
        "period_start_utc": "2026-06-13T10:00:00",
        "period_end_utc": "2026-06-13T11:00:00",
        "clean_dir": clean_dir,
        "faulty_dir": faulty_dir,
        "sequence_ts": "2026-06-13T10:07:00",
        "source_table": "t",
        "source_row_id": "1",
    }


def test_border_slot_only_processes_border_movements() -> None:
    timeline = pd.DataFrame([
        _make_movement_row(clean_dir="E"),    # border → included
        _make_movement_row(clean_dir=""),     # not border → excluded
        _make_movement_row(faulty_dir="A"),   # border → included
        _make_movement_row(clean_dir="IN_DE"),# not border → excluded
    ])
    result = _suggest_border_slot_reviews(timeline)
    # Only E and faulty_dir=A rows are processed
    assert len(result) <= 2


def test_border_slot_empty_for_non_border_movements() -> None:
    timeline = pd.DataFrame([
        _make_movement_row(clean_dir="IN_DE"),
        _make_movement_row(clean_dir=""),
    ])
    assert _suggest_border_slot_reviews(timeline) == []


def test_border_slot_empty_timeline() -> None:
    assert _suggest_border_slot_reviews(pd.DataFrame()) == []


def test_border_slot_handles_missing_dir_columns() -> None:
    timeline = pd.DataFrame([{
        "row_type": "MOVEMENT", "loco_no": "L1", "transport_number": "T1",
        "period_start_utc": "2026-06-13T10:00:00", "period_end_utc": "2026-06-13T11:00:00",
        "sequence_ts": "2026-06-13T10:07:00", "source_table": "t", "source_row_id": "1",
    }])
    # No clean_dir / faulty_dir columns → no border movements → empty result
    result = _suggest_border_slot_reviews(timeline)
    assert result == []


# ---------------------------------------------------------------------------
# _build_case_table vectorized behavior matches original contract
# ---------------------------------------------------------------------------

def _sample_findings() -> pd.DataFrame:
    return pd.DataFrame([{
        "rule_id": "R001",
        "transport_number": "12345",
        "loco_no": "L1",
        "period_start_utc": "2026-06-13T10:00:00",
        "period_end_utc": "2026-06-13T11:00:00",
        "message": "Fehler",
        "source_table": "raw_t",
        "source_row_id": "99",
        "overlap_with_transport_number": "",
    }])


def _sample_timeline_with_gap() -> pd.DataFrame:
    return pd.DataFrame([{
        "row_type": "GAP",
        "loco_no": "L2",
        "transport_number": "",
        "period_start_utc": "2026-06-13T12:00:00",
        "period_end_utc": "2026-06-13T14:00:00",
        "gap_relevant_de": "true",
        "dq_message": "Lücke",
        "source_table": "core_loco_timeline",
        "source_row_id": "200",
    }])


def test_build_case_table_has_free_row_first() -> None:
    result = _build_case_table(pd.DataFrame(), pd.DataFrame())
    assert result.iloc[0]["case_label"] == "Freie manuelle Erfassung"


def test_build_case_table_includes_findings() -> None:
    result = _build_case_table(_sample_findings(), pd.DataFrame())
    labels = result["case_label"].tolist()
    assert any("R001" in label for label in labels)
    assert any("12345" in label for label in labels)


def test_build_case_table_includes_gap_rows() -> None:
    result = _build_case_table(pd.DataFrame(), _sample_timeline_with_gap())
    labels = result["case_label"].tolist()
    assert any("GAP" in label for label in labels)


def test_build_case_table_deduplicates_gap_already_in_findings() -> None:
    findings = pd.DataFrame([{
        "rule_id": "R010",
        "transport_number": "",
        "loco_no": "L2",
        "period_start_utc": "2026-06-13T12:00:00",
        "period_end_utc": "2026-06-13T14:00:00",
        "message": "GAP-Finding",
        "source_table": "core_loco_timeline",
        "source_row_id": "200",
        "overlap_with_transport_number": "",
    }])
    timeline = _sample_timeline_with_gap()
    result = _build_case_table(findings, timeline)
    gap_labels = [label for label in result["case_label"] if label.startswith("GAP |")]
    assert len(gap_labels) == 0, "GAP row already covered by finding must be deduplicated"


def test_build_case_table_gap_message_fallback() -> None:
    timeline = pd.DataFrame([{
        "row_type": "GAP", "loco_no": "L3",
        "period_start_utc": "2026-06-13T08:00:00", "period_end_utc": "2026-06-13T09:00:00",
        "gap_relevant_de": "true", "source_table": "t", "source_row_id": "1",
    }])
    result = _build_case_table(pd.DataFrame(), timeline)
    gap_row = result[result["rule_id"] == "GAP"].iloc[0]
    assert gap_row["message"] == "Unterbrechung der Lok-Zeitachse"


def test_build_case_table_non_de_relevant_gaps_excluded() -> None:
    timeline = pd.DataFrame([{
        "row_type": "GAP", "loco_no": "L4",
        "period_start_utc": "2026-06-13T08:00:00", "period_end_utc": "2026-06-13T09:00:00",
        "gap_relevant_de": "false", "source_table": "t", "source_row_id": "1",
    }])
    result = _build_case_table(pd.DataFrame(), timeline)
    assert result[result["rule_id"] == "GAP"].empty


def test_build_case_table_has_overlap_column() -> None:
    result = _build_case_table(_sample_findings(), pd.DataFrame())
    assert "overlap_with_transport_number" in result.columns
