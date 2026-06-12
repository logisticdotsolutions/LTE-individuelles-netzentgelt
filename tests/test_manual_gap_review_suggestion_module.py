from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from manual_gap_review_suggestion_module import build_gap_review_suggestions  # noqa: E402


def _timeline(minutes: int) -> pd.DataFrame:
    start = pd.Timestamp("2026-06-10 11:25:00")
    return pd.DataFrame(
        [
            {
                "row_type": "GAP",
                "gap_relevant_de": True,
                "loco_no": "91806189201-7",
                "transport_number": "454569",
                "period_start_utc": start,
                "period_end_utc": start + pd.Timedelta(minutes=minutes),
                "source_table": "core_loco_timeline",
                "source_row_id": "99",
            }
        ]
    )


def test_gap_over_120_requires_manual_decision_without_preselection() -> None:
    assert build_gap_review_suggestions(_timeline(120)) == []

    suggestions = build_gap_review_suggestions(_timeline(121))
    assert len(suggestions) == 1
    assert suggestions[0].override_type == "CLASSIFY_GAP"
    assert suggestions[0].classification_code == ""
    assert suggestions[0].confidence == "LOW"
    assert "121 Minuten" in suggestions[0].evidence
