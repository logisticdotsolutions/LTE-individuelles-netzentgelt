from __future__ import annotations

from datetime import date
from pathlib import Path
import sys
import tempfile

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "payload" / "scripts"))

from operational_day_filter_module import (  # noqa: E402
    default_operational_day,
    filter_by_operational_days,
    normalize_day_range,
    summarize_no_loco_cases,
)


def main() -> None:
    assert default_operational_day(date(2026, 6, 8)) == date(2026, 6, 6)
    assert normalize_day_range(date(2026, 6, 7), date(2026, 6, 6)) == (date(2026, 6, 6), date(2026, 6, 7))

    frame = pd.DataFrame(
        {
            "actual_departure_ts": [
                "2026-06-05T23:59:59",
                "2026-06-06T00:00:00",
                "2026-06-06T23:59:59",
                "2026-06-07T00:00:00",
                "",
            ],
            "period_start_utc": [
                "2026-06-05T23:59:59",
                "2026-06-06T00:00:00",
                "2026-06-06T23:59:59",
                "2026-06-07T00:00:00",
                "2026-06-06T12:00:00",
            ],
            "id": ["before", "start", "end", "after", "gap-fallback"],
        }
    )
    filtered = filter_by_operational_days(
        frame,
        date_from=date(2026, 6, 6),
        date_to=date(2026, 6, 6),
        timestamp_candidates=["actual_departure_ts", "period_start_utc"],
    )
    assert filtered["id"].tolist() == ["start", "end", "gap-fallback"]

    cases = pd.DataFrame(
        {
            "Quelle": ["TransportDetail.csv", "TransportDetail.csv", "LocomotiveMovement.csv"],
            "TransportNumber": ["T1", "T2", "T3"],
            "Erstes Datum": ["06.06.2026 01:00", "07.06.2026 01:00", "06.06.2026 22:30"],
            "Anzahl Zeilen": [2, 5, 3],
        }
    )
    filtered_cases = filter_by_operational_days(
        cases,
        date_from=date(2026, 6, 6),
        date_to=date(2026, 6, 6),
        timestamp_candidates=["Erstes Datum"],
    )
    assert filtered_cases["TransportNumber"].tolist() == ["T1", "T3"]

    fallback = pd.DataFrame(
        {
            "Quelle": ["TransportDetail.csv", "LocomotiveMovement.csv"],
            "Prüfung": ["A", "B"],
            "Anzahl Zeilen": [99, 99],
            "Betroffene Transporte": [99, 99],
            "Status": ["OK", "OK"],
        }
    )
    summary = summarize_no_loco_cases(filtered_cases, fallback)
    counts = dict(zip(summary["Quelle"], summary["Anzahl Zeilen"]))
    assert counts == {"TransportDetail.csv": 2, "LocomotiveMovement.csv": 3}
    print("PHASE5C LOGIKTEST erfolgreich.")


if __name__ == "__main__":
    main()
