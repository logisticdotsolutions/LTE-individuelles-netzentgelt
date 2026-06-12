from pathlib import Path
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import vens_selection_ui_module as module


def test_case_rows_keep_only_rows_with_performing_ru() -> None:
    timeline = pd.DataFrame([
        {
            "performing_ru": "LTE DE - LTE Germany GmbH",
            "loco_no": "91801234567-8",
            "transport_number": "T-001",
            "period_start_utc": "2026-06-12T08:00:00Z",
            "period_end_utc": "2026-06-12T10:00:00Z",
        },
        {
            "performing_ru": "",
            "loco_no": "91801234567-8",
            "transport_number": "T-002",
            "period_start_utc": "2026-06-12T11:00:00Z",
            "period_end_utc": "2026-06-12T12:00:00Z",
        },
    ])

    result = module._case_rows(timeline)

    assert len(result) == 1
    assert "LTE DE - LTE Germany GmbH" in result.iloc[0]["_label"]
    assert "T-001" in result.iloc[0]["_label"]


def test_case_rows_return_empty_without_performing_ru_column() -> None:
    assert module._case_rows(pd.DataFrame([{"loco_no": "91801234567-8"}])).empty
