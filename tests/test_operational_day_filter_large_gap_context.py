from __future__ import annotations

from datetime import date
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from operational_day_filter_module import filter_by_operational_days  # noqa: E402


def test_large_gap_adds_previous_and_following_movement_context() -> None:
    timeline = pd.DataFrame(
        {
            "row_type": ["MOVEMENT", "GAP", "MOVEMENT", "MOVEMENT"],
            "loco_no": ["91806189201-7"] * 4,
            "actual_departure_ts": [
                "2026-06-06T15:00:00",
                "",
                "2026-06-08T11:00:00",
                "2026-06-09T10:00:00",
            ],
            "period_start_utc": [
                "2026-06-06T15:00:00",
                "2026-06-06T16:00:00",
                "2026-06-08T11:00:00",
                "2026-06-09T10:00:00",
            ],
            "period_end_utc": [
                "2026-06-06T16:00:00",
                "2026-06-08T11:00:00",
                "2026-06-08T14:00:00",
                "2026-06-09T12:00:00",
            ],
            "gap_from_utc": ["", "2026-06-06T16:00:00", "", ""],
            "gap_to_utc": ["", "2026-06-08T11:00:00", "", ""],
            "gap_duration_minutes": [None, 2580, None, None],
            "gap_relevant_de": [False, True, False, False],
            "id": ["previous", "big-gap", "following", "later"],
        }
    )

    filtered = filter_by_operational_days(
        timeline,
        date_from=date(2026, 6, 7),
        date_to=date(2026, 6, 7),
        timestamp_candidates=["actual_departure_ts", "period_start_utc"],
    )

    assert filtered["id"].tolist() == ["previous", "big-gap", "following"]


def test_small_gap_does_not_pull_movements_from_other_days_into_context() -> None:
    timeline = pd.DataFrame(
        {
            "row_type": ["MOVEMENT", "GAP", "MOVEMENT"],
            "loco_no": ["91806189201-7"] * 3,
            "actual_departure_ts": ["2026-06-06T22:00:00", "", "2026-06-07T01:00:00"],
            "period_start_utc": [
                "2026-06-06T22:00:00",
                "2026-06-06T23:00:00",
                "2026-06-07T01:00:00",
            ],
            "period_end_utc": [
                "2026-06-06T23:00:00",
                "2026-06-07T01:00:00",
                "2026-06-07T02:00:00",
            ],
            "gap_from_utc": ["", "2026-06-06T23:00:00", ""],
            "gap_to_utc": ["", "2026-06-07T01:00:00", ""],
            "gap_duration_minutes": [None, 120, None],
            "gap_relevant_de": [False, True, False],
            "id": ["previous", "small-gap", "following"],
        }
    )

    filtered = filter_by_operational_days(
        timeline,
        date_from=date(2026, 6, 7),
        date_to=date(2026, 6, 7),
        timestamp_candidates=["actual_departure_ts", "period_start_utc"],
    )

    assert filtered["id"].tolist() == ["small-gap", "following"]
