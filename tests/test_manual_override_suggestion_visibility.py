from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from manual_override_suggestion_visibility_module import hide_accepted_active_suggestions  # noqa: E402
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
