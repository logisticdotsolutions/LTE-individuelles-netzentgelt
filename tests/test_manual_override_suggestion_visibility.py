from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import manual_override_gap_policy_runtime_module as gap_policy_runtime  # noqa: E402
import manual_override_suggestion_module as suggestion_module  # noqa: E402


def _movement(
    loco_no: str,
    sequence_no: int,
    performing_ru: str,
    origin_location: str,
    destination_location: str,
) -> dict[str, object]:
    return {
        "row_type": "MOVEMENT",
        "loco_no": loco_no,
        "sequence_no": sequence_no,
        "performing_ru": performing_ru,
        "origin_location": origin_location,
        "destination_location": destination_location,
        "transport_number": f"T-{loco_no}-{sequence_no}",
        "source_table": "test",
        "source_row_id": f"RID-{loco_no}-{sequence_no}",
    }


def _timeline(gap_minutes: int) -> pd.DataFrame:
    first = _movement("L1", 1, "LTE DE", "A", "B")
    second = _movement("L1", 2, "LTE DE", "B", "C")
    first["period_start_utc"] = "2026-06-01T08:00:00"
    first["period_end_utc"] = "2026-06-01T09:00:00"
    first["sequence_ts"] = "2026-06-01T08:00:00"
    second["period_start_utc"] = pd.Timestamp("2026-06-01T09:00:00") + pd.Timedelta(minutes=gap_minutes)
    second["period_end_utc"] = pd.Timestamp(second["period_start_utc"]) + pd.Timedelta(hours=1)
    second["sequence_ts"] = second["period_start_utc"]
    return pd.DataFrame([first, second])


def _suggestions(timeline: pd.DataFrame) -> pd.DataFrame:
    gap_policy_runtime.install_gap_policy_labels()
    return suggestion_module.build_suggestion_table(
        db_path=Path("does_not_exist.duckdb"),
        findings=pd.DataFrame(),
        timeline=timeline,
    )


def _types(timeline: pd.DataFrame) -> list[tuple[str, str]]:
    result = _suggestions(timeline)
    return list(zip(result["suggestion_type"], result["classification_code"]))


def test_short_gap_keeps_performing_ru_suggestion_visible() -> None:
    assert ("GAP_PERFORMING_RU_FROM_BOTH_NEIGHBOURS", "SAME_RU_CONTINUITY") in _types(_timeline(30))


def test_open_gap_no_longer_creates_no_lte_assignment_suggestion() -> None:
    row = _movement("L2", 1, "LTE DE", "A", "B")
    row["period_start_utc"] = "2026-06-01T08:00:00"
    row["period_end_utc"] = "2026-06-01T09:00:00"
    row["sequence_ts"] = "2026-06-01T08:00:00"
    row["source_snapshot_at_utc"] = "2026-06-01T14:30:00"

    result = _suggestions(pd.DataFrame([row]))

    assert ("GAP_NO_LTE_ASSIGNMENT", "NO_LTE_ASSIGNMENT") not in _types(pd.DataFrame([row]))
    assert result.empty


def _matrix_timeline(gap_minutes: int, *, ru_same: bool = True, origin_after: str = "XX") -> pd.DataFrame:
    first = _movement("M", 1, "RU-A", "AA", "XX")
    second = _movement("M", 2, "RU-A" if ru_same else "RU-B", origin_after, "BB")
    first["period_start_utc"] = "2026-06-01T08:00:00"
    first["period_end_utc"] = "2026-06-01T09:00:00"
    first["sequence_ts"] = "2026-06-01T08:00:00"
    second["period_start_utc"] = pd.Timestamp("2026-06-01T09:00:00") + pd.Timedelta(minutes=gap_minutes)
    second["period_end_utc"] = pd.Timestamp(second["period_start_utc"]) + pd.Timedelta(hours=1)
    second["sequence_ts"] = second["period_start_utc"]
    return pd.DataFrame([first, second])


def _matrix_types(timeline: pd.DataFrame) -> list[tuple[str, str]]:
    gap_policy_runtime.install_gap_policy_labels()
    result = suggestion_module.build_suggestion_table(
        db_path=Path("does_not_exist.duckdb"),
        findings=pd.DataFrame(),
        timeline=timeline,
    )
    return list(zip(result["suggestion_type"], result["classification_code"]))


def test_matrix_short_gap_under_120_gets_same_ru_proposal() -> None:
    assert ("GAP_PERFORMING_RU_FROM_BOTH_NEIGHBOURS", "SAME_RU_CONTINUITY") in _matrix_types(_matrix_timeline(60))


def test_matrix_121_to_599_gets_cold_stand() -> None:
    assert ("POSSIBLE_COLD_STAND_SAME_LOCATION", "COLD_STAND") in _matrix_types(_matrix_timeline(121))
    assert ("POSSIBLE_COLD_STAND_SAME_LOCATION", "COLD_STAND") in _matrix_types(_matrix_timeline(599))


def test_matrix_over_600_gets_no_assignment() -> None:
    assert ("GAP_NO_LTE_ASSIGNMENT", "NO_LTE_ASSIGNMENT") in _matrix_types(_matrix_timeline(601))


def test_matrix_location_break_gets_no_assignment_independent_of_duration() -> None:
    assert ("GAP_NO_LTE_ASSIGNMENT", "NO_LTE_ASSIGNMENT") in _matrix_types(_matrix_timeline(30, origin_after="YY"))


def test_matrix_open_gap_uses_minimum_duration_from_latest_update() -> None:
    row = _movement("O", 1, "RU-A", "AA", "XX")
    row["period_start_utc"] = "2026-06-01T08:00:00"
    row["period_end_utc"] = "2026-06-01T09:00:00"
    row["sequence_ts"] = "2026-06-01T08:00:00"
    row["source_snapshot_at_utc"] = "2026-06-01T14:30:00"
    result = _matrix_types(pd.DataFrame([row]))
    assert ("GAP_NO_LTE_ASSIGNMENT", "NO_LTE_ASSIGNMENT") not in result
    assert result == []
