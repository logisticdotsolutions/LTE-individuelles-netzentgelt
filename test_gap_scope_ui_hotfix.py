from __future__ import annotations

import pandas as pd


def relevant_gap_rows(timeline: pd.DataFrame) -> pd.DataFrame:
    gap_mask = timeline["row_type"].fillna("").astype(str).str.upper().eq("GAP")
    if "gap_relevant_de" in timeline.columns:
        gap_mask = gap_mask & (
            timeline["gap_relevant_de"]
            .fillna(False)
            .astype(str)
            .str.strip()
            .str.lower()
            .isin(["true", "1", "yes", "y", "ja"])
        )
    return timeline[gap_mask]


def main() -> int:
    timeline = pd.DataFrame(
        [
            {"row_type": "MOVEMENT", "gap_relevant_de": "true", "loco_no": "L1"},
            {"row_type": "GAP", "gap_relevant_de": "true", "loco_no": "L1", "period_start_utc": "2026-06-06T01:00:00"},
            {"row_type": "GAP", "gap_relevant_de": "false", "loco_no": "L1", "period_start_utc": "2026-06-06T02:00:00"},
            {"row_type": "GAP", "gap_relevant_de": "", "loco_no": "L1", "period_start_utc": "2026-06-06T03:00:00"},
            {"row_type": "GAP", "gap_relevant_de": 1, "loco_no": "L2", "period_start_utc": "2026-06-06T04:00:00"},
            {"row_type": "GAP", "gap_relevant_de": "JA", "loco_no": "L3", "period_start_utc": "2026-06-06T05:00:00"},
        ]
    )
    result = relevant_gap_rows(timeline)
    assert len(result) == 3, result
    assert set(result["period_start_utc"].tolist()) == {
        "2026-06-06T01:00:00",
        "2026-06-06T04:00:00",
        "2026-06-06T05:00:00",
    }

    legacy = pd.DataFrame([
        {"row_type": "GAP", "loco_no": "L1"},
        {"row_type": "MOVEMENT", "loco_no": "L1"},
    ])
    legacy_result = relevant_gap_rows(legacy)
    assert len(legacy_result) == 1, legacy_result

    print("OK: Nur explizit DE-relevante GAPs werden im modernen Schema angeboten.")
    print("OK: Legacy-Timeline ohne gap_relevant_de bleibt defensiv lauffähig.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
