from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import fallpruefung_review_runtime_bridge as module  # noqa: E402


def _gap(minutes: int, relevant: bool = True) -> pd.DataFrame:
    start = pd.Timestamp("2026-06-09 10:00:00")
    return pd.DataFrame([
        {
            "row_type": "GAP",
            "loco_no": "91801234567-8",
            "period_start_utc": start,
            "period_end_utc": start + pd.Timedelta(minutes=minutes),
            "gap_duration_minutes": minutes,
            "gap_relevant_de": relevant,
            "transport_number": "T-001",
            "source_table": "core_loco_timeline",
            "source_row_id": "gap-1",
        }
    ])


def test_explicit_de_gap_requires_more_than_120_minutes() -> None:
    assert module._build_gap_cold_stand_suggestions(_gap(120)) == []
    assert module._build_gap_cold_stand_suggestions(_gap(121, relevant=False)) == []

    result = module._build_gap_cold_stand_suggestions(_gap(121))

    assert len(result) == 1
    assert result[0].suggestion_type == module.COLD_STAND_SUGGESTION_TYPE
    assert result[0].classification_code == "COLD_STAND"
    assert result[0].override_type == "CLASSIFY_GAP"
