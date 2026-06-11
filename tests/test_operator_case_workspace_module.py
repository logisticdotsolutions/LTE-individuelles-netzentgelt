from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from operator_case_workspace_module import (  # noqa: E402
    build_border_crossing_view,
    build_gap_view,
    filter_loco_rows,
    sort_operator_table,
)


def test_sort_operator_table_orders_by_loco_number_first() -> None:
    data = pd.DataFrame(
        [
            {"Loknummer": "200", "Datum": "02.06.2026", "Transportnummer": "T2"},
            {"Loknummer": "100", "Datum": "03.06.2026", "Transportnummer": "T3"},
            {"Loknummer": "100", "Datum": "01.06.2026", "Transportnummer": "T1"},
        ]
    )

    result = sort_operator_table(data)

    assert result["Loknummer"].tolist() == ["100", "100", "200"]
    assert result["Transportnummer"].tolist() == ["T1", "T3", "T2"]


def test_filter_loco_rows_accepts_technical_loco_column() -> None:
    data = pd.DataFrame(
        [
            {"loco_no": "9180", "transport_number": "A"},
            {"loco_no": "9181", "transport_number": "B"},
        ]
    )

    result = filter_loco_rows(data, "9181")

    assert result["transport_number"].tolist() == ["B"]


def test_build_gap_view_calculates_gap_minutes() -> None:
    timeline = pd.DataFrame(
        [
            {
                "loco_no": "9180",
                "row_type": "GAP",
                "period_start_utc": "2026-06-08 03:00:00",
                "period_end_utc": "2026-06-08 05:30:00",
                "gap_relevant_de": True,
                "performing_ru": "LTE DE",
                "transport_number": "T1",
                "gap_message": "Unterbrechung",
            }
        ]
    )

    result = build_gap_view(timeline, "9180")

    assert result["Dauer (Minuten)"].tolist() == [150]
    assert result["DE-relevant"].tolist() == [True]


def test_build_border_crossing_view_filters_entry_and_exit_rows() -> None:
    timeline = pd.DataFrame(
        [
            {"loco_no": "9180", "de_event_label": "Einfahrt", "sequence_ts": "2026-06-08 03:00:00"},
            {"loco_no": "9180", "de_event_label": "In DE", "sequence_ts": "2026-06-08 04:00:00"},
            {"loco_no": "9180", "de_event_label": "Ausfahrt", "sequence_ts": "2026-06-08 05:00:00"},
        ]
    )

    result = build_border_crossing_view(timeline, "9180")

    assert result["Ereignis"].tolist() == ["Einfahrt", "Ausfahrt"]
