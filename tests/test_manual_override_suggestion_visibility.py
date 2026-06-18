from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from manual_override_suggestion_visibility_module import hide_accepted_active_suggestions  # noqa: E402
import manual_override_gap_policy_runtime_module as gap_policy_runtime  # noqa: E402
import manual_override_suggestion_module as suggestion_module  # noqa: E402


def test_accepted_suggestion_is_hidden_while_override_is_active(tmp_path: Path) -> None:
    acceptance_log = tmp_path / "manual_override_suggestion_acceptance_log.csv"
    pd.DataFrame(
        {
            "suggestion_id": ["SUG_KEEP_HIDDEN", "SUG_RESHOW"],
            "override_id": ["OVR_ACTIVE", "OVR_INACTIVE"],
        }
    ).to_csv(acceptance_log, sep=";", index=False, encoding="utf-8-sig")

    overrides = pd.DataFrame(
        {
            "override_id": ["OVR_ACTIVE", "OVR_INACTIVE"],
            "active_flag": ["Y", "N"],
        }
    )
    suggestions = pd.DataFrame(
        {
            "suggestion_id": ["SUG_KEEP_HIDDEN", "SUG_RESHOW", "SUG_NEW"],
            "suggested_value": ["A", "B", "C"],
        }
    )

    visible = hide_accepted_active_suggestions(
        suggestions,
        acceptance_log_path=acceptance_log,
        overrides=overrides,
    )

    assert visible["suggestion_id"].tolist() == ["SUG_RESHOW", "SUG_NEW"]


def _movement(loco: str, seq: int, ru: str, origin: str, destination: str) -> dict[str, object]:
    return {
        "row_type": "MOVEMENT",
        "loco_no": loco,
        "sort_sequence": seq,
        "period_start_utc": f"2026-06-01T{8 + seq:02d}:00:00",
        "period_end_utc": f"2026-06-01T{9 + seq:02d}:00:00",
        "sequence_ts": f"2026-06-01T{8 + seq:02d}:00:00",
        "source_table": "core_loco_timeline",
        "source_row_id": seq,
        "transport_number": f"T{seq}",
        "performing_ru": ru,
        "origin_name": origin,
        "destination_name": destination,
        "gap_relevant_de": "false",
        "gap_duration_minutes": "",
    }


def _gap(loco: str, seq: int, minutes: int, origin: str, destination: str) -> dict[str, object]:
    return {
        "row_type": "GAP",
        "loco_no": loco,
        "sort_sequence": seq,
        "period_start_utc": f"2026-06-01T{8 + seq:02d}:00:00",
        "period_end_utc": f"2026-06-01T{9 + seq:02d}:00:00",
        "sequence_ts": f"2026-06-01T{8 + seq:02d}:00:00",
        "source_table": "core_loco_timeline",
        "source_row_id": seq,
        "transport_number": "",
        "performing_ru": "",
        "origin_name": origin,
        "destination_name": destination,
        "gap_relevant_de": "true",
        "gap_duration_minutes": minutes,
    }


def _one_gap_result(rows: list[dict[str, object]]) -> tuple[str, str]:
    result = suggestion_module._suggest_gap_decisions(pd.DataFrame(rows))
    assert len(result) == 1
    return result[0].suggestion_type, result[0].classification_code


def test_short_same_ru_gap_gets_evu_takeover_only() -> None:
    assert _one_gap_result(
        [
            _movement("A", 1, "RU-A", "AA", "XX"),
            _gap("A", 2, 60, "XX", "XX"),
            _movement("A", 3, "RU-A", "XX", "BB"),
        ]
    ) == ("GAP_PERFORMING_RU_FROM_BOTH_NEIGHBOURS", "SAME_RU_CONTINUITY")


def test_long_same_ru_gap_without_location_jump_gets_cold_stand_only() -> None:
    assert _one_gap_result(
        [
            _movement("B", 1, "RU-A", "AA", "XX"),
            _gap("B", 2, 181, "XX", "XX"),
            _movement("B", 3, "RU-A", "XX", "BB"),
        ]
    ) == ("POSSIBLE_COLD_STAND_SAME_LOCATION", "COLD_STAND")


def test_location_jump_gets_no_lte_assignment_only() -> None:
    assert _one_gap_result(
        [
            _movement("C", 1, "RU-A", "AA", "XX"),
            _gap("C", 2, 60, "XX", "YY"),
            _movement("C", 3, "RU-A", "YY", "BB"),
        ]
    ) == ("GAP_NO_LTE_ASSIGNMENT", "NO_LTE_ASSIGNMENT")


def test_open_long_gap_gets_no_lte_assignment_only() -> None:
    assert _one_gap_result(
        [
            _movement("D", 1, "RU-A", "AA", "XX"),
            _gap("D", 2, 181, "XX", ""),
        ]
    ) == ("GAP_NO_LTE_ASSIGNMENT", "NO_LTE_ASSIGNMENT")


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
    assert ("GAP_NO_LTE_ASSIGNMENT", "NO_LTE_ASSIGNMENT") in result
