from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from manual_override_gap_policy_runtime_module import install_gap_policy_labels  # noqa: E402
import manual_override_suggestion_module as suggestion_module  # noqa: E402


def _movement(*, seq: int, transport: str, start: str, end: str, origin: str, destination: str, ru: str, snapshot: str = "") -> dict[str, object]:
    return {
        "row_type": "MOVEMENT",
        "loco_no": "918012345678",
        "transport_number": transport,
        "performing_ru": ru,
        "sort_sequence": seq,
        "sequence_ts": start,
        "period_start_utc": start,
        "period_end_utc": end,
        "origin_name": origin,
        "destination_name": destination,
        "source_table": "core_loco_timeline",
        "source_row_id": seq,
        "source_snapshot_at_utc": snapshot,
    }


def _gap_suggestions(timeline: pd.DataFrame) -> pd.DataFrame:
    install_gap_policy_labels()
    suggestions = suggestion_module.build_suggestion_table(
        db_path=Path("missing_test_database.duckdb"),
        findings=pd.DataFrame(),
        timeline=timeline,
    )
    if suggestions.empty:
        return suggestions
    kind = suggestions["suggestion_type"].fillna("").astype(str)
    return suggestions[
        kind.str.startswith("GAP")
        | kind.eq("POSSIBLE_COLD_STAND_SAME_LOCATION")
    ].reset_index(drop=True)


def test_gap_under_120_same_location_same_evu_suggests_same_evu() -> None:
    timeline = pd.DataFrame([
        _movement(seq=1, transport="T1", start="2026-06-18T08:00:00", end="2026-06-18T09:00:00", origin="A", destination="B", ru="LTE DE - LTE Germany GmbH"),
        _movement(seq=2, transport="T2", start="2026-06-18T10:30:00", end="2026-06-18T11:00:00", origin="B", destination="C", ru="LTE DE - LTE Germany GmbH"),
    ])

    suggestions = _gap_suggestions(timeline)

    assert len(suggestions) == 1
    row = suggestions.iloc[0]
    assert row["suggestion_type"] == "GAP_PERFORMING_RU_FROM_BOTH_NEIGHBOURS"
    assert row["classification_code"] == "SAME_RU_CONTINUITY"
    assert row["suggested_value"] == "LTE DE - LTE Germany GmbH"


def test_gap_between_120_and_600_known_end_same_location_suggests_cold_stand() -> None:
    timeline = pd.DataFrame([
        _movement(seq=1, transport="T1", start="2026-06-18T08:00:00", end="2026-06-18T09:00:00", origin="A", destination="B", ru="LTE DE - LTE Germany GmbH"),
        _movement(seq=2, transport="T2", start="2026-06-18T13:00:00", end="2026-06-18T14:00:00", origin="B", destination="C", ru="LTE NL - LTE Netherlands B.V."),
    ])

    suggestions = _gap_suggestions(timeline)

    assert len(suggestions) == 1
    row = suggestions.iloc[0]
    assert row["suggestion_type"] == "POSSIBLE_COLD_STAND_SAME_LOCATION"
    assert row["classification_code"] == "COLD_STAND"


def test_gap_over_600_known_end_same_location_suggests_no_assignment() -> None:
    timeline = pd.DataFrame([
        _movement(seq=1, transport="T1", start="2026-06-18T08:00:00", end="2026-06-18T09:00:00", origin="A", destination="B", ru="LTE DE - LTE Germany GmbH"),
        _movement(seq=2, transport="T2", start="2026-06-18T20:00:00", end="2026-06-18T21:00:00", origin="B", destination="C", ru="LTE NL - LTE Netherlands B.V."),
    ])

    suggestions = _gap_suggestions(timeline)

    assert len(suggestions) == 1
    row = suggestions.iloc[0]
    assert row["suggestion_type"] == "GAP_NO_LTE_ASSIGNMENT"
    assert row["classification_code"] == "NO_LTE_ASSIGNMENT"


def test_gap_location_jump_always_suggests_no_assignment() -> None:
    timeline = pd.DataFrame([
        _movement(seq=1, transport="T1", start="2026-06-18T08:00:00", end="2026-06-18T09:00:00", origin="A", destination="B", ru="LTE DE - LTE Germany GmbH"),
        _movement(seq=2, transport="T2", start="2026-06-18T09:45:00", end="2026-06-18T10:00:00", origin="X", destination="C", ru="LTE DE - LTE Germany GmbH"),
    ])

    suggestions = _gap_suggestions(timeline)

    assert len(suggestions) == 1
    row = suggestions.iloc[0]
    assert row["suggestion_type"] == "GAP_NO_LTE_ASSIGNMENT"
    assert row["classification_code"] == "NO_LTE_ASSIGNMENT"


def test_gap_without_end_creates_no_gap_suggestion() -> None:
    timeline = pd.DataFrame([
        _movement(seq=1, transport="T1", start="2026-06-18T08:00:00", end="2026-06-18T09:00:00", origin="A", destination="B", ru="LTE DE - LTE Germany GmbH", snapshot="2026-06-18T13:30:00"),
    ])

    suggestions = _gap_suggestions(timeline)

    assert suggestions.empty
