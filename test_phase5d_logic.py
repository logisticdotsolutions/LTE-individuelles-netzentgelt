from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parent
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from manual_override_batch_module import create_overrides_from_selected_suggestions
from manual_override_module import OVERRIDE_COLUMNS
from manual_override_suggestion_module import _suggest_gap_performing_ru_from_neighbours


def movement(sort_sequence: float, ru: str, transport: str, start: str, end: str, row_id: int) -> dict[str, object]:
    return {
        "row_type": "MOVEMENT",
        "loco_no": "91806189042-7",
        "sort_sequence": sort_sequence,
        "period_start_utc": start,
        "period_end_utc": end,
        "performing_ru": ru,
        "transport_number": transport,
        "source_table": "raw_locomotivemovement",
        "source_row_id": row_id,
        "gap_relevant_de": False,
    }


def gap(sort_sequence: float, start: str, end: str, row_id: int) -> dict[str, object]:
    return {
        "row_type": "GAP",
        "loco_no": "91806189042-7",
        "sort_sequence": sort_sequence,
        "period_start_utc": start,
        "period_end_utc": end,
        "performing_ru": "",
        "transport_number": "T100",
        "source_table": "raw_locomotivemovement",
        "source_row_id": row_id,
        "gap_relevant_de": True,
    }


def main() -> None:
    timeline = pd.DataFrame(
        [
            movement(1.0, "LTE NL", "T100", "2026-06-06T01:00:00", "2026-06-06T03:00:00", 1),
            gap(1.5, "2026-06-06T03:00:00", "2026-06-06T05:00:00", 2),
            movement(2.0, "LTE NL", "T101", "2026-06-06T05:00:00", "2026-06-06T07:00:00", 3),
        ]
    )
    suggestions = _suggest_gap_performing_ru_from_neighbours(timeline)
    assert len(suggestions) == 1, suggestions
    suggestion = suggestions[0].to_dict()
    assert suggestion["suggestion_type"] == "GAP_PERFORMING_RU_FROM_BOTH_NEIGHBOURS"
    assert suggestion["override_type"] == "CLASSIFY_GAP"
    assert suggestion["classification_code"] == "SAME_RU_CONTINUITY"
    assert suggestion["confidence"] == "HIGH"
    assert suggestion["suggested_value"] == "LTE NL"

    conflict_timeline = timeline.copy()
    conflict_timeline.loc[2, "performing_ru"] = "LTE DE"
    assert _suggest_gap_performing_ru_from_neighbours(conflict_timeline) == []

    suggestion_df = pd.DataFrame([suggestion])
    overrides = pd.DataFrame(columns=OVERRIDE_COLUMNS)
    updated, created, skipped = create_overrides_from_selected_suggestions(
        overrides=overrides,
        suggestions=suggestion_df,
        selected_suggestion_ids=[suggestion["suggestion_id"]],
        created_by="phase5d-test",
        comment="Fachlich kontrolliert.",
        now_text="2026-06-08T08:00:00Z",
    )
    assert len(updated) == 1
    assert len(created) == 1
    assert skipped == []
    assert updated.iloc[0]["override_type"] == "CLASSIFY_GAP"
    assert updated.iloc[0]["override_value"] == "LTE NL"
    assert updated.iloc[0]["classification_code"] == "SAME_RU_CONTINUITY"

    updated_again, created_again, skipped_again = create_overrides_from_selected_suggestions(
        overrides=updated,
        suggestions=suggestion_df,
        selected_suggestion_ids=[suggestion["suggestion_id"]],
        created_by="phase5d-test",
        comment="Nochmals kontrolliert.",
        now_text="2026-06-08T08:01:00Z",
    )
    assert len(updated_again) == 1
    assert created_again == []
    assert len(skipped_again) == 1
    assert "bereits vorhanden" in skipped_again[0].reason

    print("OK: GAP-PerformingRU-Vorschlag aus identischen direkten Nachbarn")
    print("OK: Kein Vorschlag bei widerspruechlichen Nachbar-PerformingRUs")
    print("OK: Checkmark-Sammeluebernahme erzeugt auditierbaren CLASSIFY_GAP-Override")
    print("OK: Fachlich identische aktive Overrides werden nicht dupliziert")


if __name__ == "__main__":
    main()
