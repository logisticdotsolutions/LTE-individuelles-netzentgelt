from __future__ import annotations

from datetime import date
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from operational_day_filter_module import filter_by_operational_days  # noqa: E402


def test_cross_day_gap_remains_visible_on_each_affected_day() -> None:
    timeline = pd.DataFrame(
        {
            "row_type": ["MOVEMENT", "GAP", "GAP", "GAP", "MOVEMENT"],
            "actual_departure_ts": [
                "2026-06-07T10:00:00",
                "",
                "",
                "",
                "2026-06-06T12:00:00",
            ],
            "period_start_utc": [
                "2026-06-07T10:00:00",
                "2026-06-06T20:45:00",
                "2026-06-06T20:45:00",
                "2026-06-07T00:00:00",
                "2026-06-06T12:00:00",
            ],
            "period_end_utc": [
                "2026-06-07T11:00:00",
                "2026-06-07T11:15:00",
                "2026-06-07T00:00:00",
                "2026-06-07T01:00:00",
                "2026-06-06T13:00:00",
            ],
            "gap_from_utc": [
                "",
                "2026-06-06T20:45:00",
                "2026-06-06T20:45:00",
                "2026-06-07T00:00:00",
                "",
            ],
            "gap_to_utc": [
                "",
                "2026-06-07T11:15:00",
                "2026-06-07T00:00:00",
                "2026-06-07T01:00:00",
                "",
            ],
            "id": [
                "movement-on-selected-day",
                "gap-started-day-before",
                "gap-ends-exactly-at-midnight",
                "gap-starts-exactly-at-midnight",
                "movement-day-before",
            ],
        }
    )

    filtered = filter_by_operational_days(
        timeline,
        date_from=date(2026, 6, 7),
        date_to=date(2026, 6, 7),
        timestamp_candidates=["actual_departure_ts", "period_start_utc"],
    )

    assert filtered["id"].tolist() == [
        "movement-on-selected-day",
        "gap-started-day-before",
        "gap-starts-exactly-at-midnight",
    ]


def test_non_gap_rows_still_follow_the_first_available_time_anchor() -> None:
    movements = pd.DataFrame(
        {
            "row_type": ["MOVEMENT", "MOVEMENT"],
            "actual_departure_ts": ["2026-06-06T23:59:59", "2026-06-07T00:00:00"],
            "period_start_utc": ["2026-06-07T10:00:00", "2026-06-06T10:00:00"],
            "id": ["departure-day-before", "departure-on-selected-day"],
        }
    )

    filtered = filter_by_operational_days(
        movements,
        date_from=date(2026, 6, 7),
        date_to=date(2026, 6, 7),
        timestamp_candidates=["actual_departure_ts", "period_start_utc"],
    )

    assert filtered["id"].tolist() == ["departure-on-selected-day"]
