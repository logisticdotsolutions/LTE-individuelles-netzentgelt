from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from case_timeline_context_module import load_case_timeline_context  # noqa: E402


def test_load_case_timeline_context_keeps_latest_30_calendar_days(tmp_path: Path) -> None:
    path = tmp_path / "core_loco_timeline.csv"
    pd.DataFrame(
        [
            {"loco_no": "OLD", "period_start_utc": "2026-04-30 12:00:00"},
            {"loco_no": "BOUNDARY", "period_start_utc": "2026-05-13 00:00:00"},
            {"loco_no": "LATEST", "period_start_utc": "2026-06-11 10:00:00"},
        ]
    ).to_csv(path, sep=";", index=False, encoding="utf-8-sig")

    result = load_case_timeline_context(path=path, lookback_days=30)

    assert result["loco_no"].tolist() == ["BOUNDARY", "LATEST"]


def test_load_case_timeline_context_keeps_rows_without_timestamp_for_audit(tmp_path: Path) -> None:
    path = tmp_path / "core_loco_timeline.csv"
    pd.DataFrame(
        [
            {"loco_no": "UNKNOWN", "period_start_utc": ""},
            {"loco_no": "LATEST", "period_start_utc": "2026-06-11 10:00:00"},
        ]
    ).to_csv(path, sep=";", index=False, encoding="utf-8-sig")

    result = load_case_timeline_context(path=path, lookback_days=30)

    assert result["loco_no"].tolist() == ["UNKNOWN", "LATEST"]
