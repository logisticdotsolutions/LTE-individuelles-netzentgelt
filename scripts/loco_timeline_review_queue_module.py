from __future__ import annotations

import pandas as pd

from loco_timeline_calendar_runtime_module import PROBLEM_STATUSES, STATUS_PRIORITY, _join_unique

REVIEW_QUEUE_COLUMNS = [
    "Auswahl",
    "Meldetag",
    "Loknummer",
    "Status",
    "StatusPriorität",
    "Halter",
    "Nutzer / PerformingRU",
    "Problemsegmente",
    "Regeln",
    "Meldung",
    "Begründung",
    "Erste Uhrzeit",
    "Letzte Uhrzeit",
]
EMPTY_REVIEW_QUEUE = pd.DataFrame(columns=REVIEW_QUEUE_COLUMNS)


def _status_from_priority(priority: object) -> str:
    try:
        numeric_priority = int(priority)
    except (TypeError, ValueError):
        numeric_priority = 0
    priority_to_status = {value: key for key, value in STATUS_PRIORITY.items()}
    return priority_to_status.get(numeric_priority, "Außerhalb DE")


def _minute_to_time(value: object) -> str:
    if pd.isna(value):
        return ""
    minute = int(value)
    if minute >= 24 * 60:
        return "24:00"
    minute = max(0, minute)
    return f"{minute // 60:02d}:{minute % 60:02d}"


def build_loco_timeline_review_queue(segments_df: pd.DataFrame) -> pd.DataFrame:
    """Build a problem-oriented queue of locomotive days from timeline segments."""
    if segments_df.empty:
        return EMPTY_REVIEW_QUEUE.copy()

    problems = segments_df[segments_df["Status"].isin(PROBLEM_STATUSES)].copy()
    if problems.empty:
        return EMPTY_REVIEW_QUEUE.copy()

    grouped = (
        problems.groupby(["Meldetag", "Loknummer"], dropna=False)
        .agg(
            StatusPriorität=("StatusPriorität", "max"),
            Halter=("Halter", _join_unique),
            **{
                "Nutzer / PerformingRU": ("Nutzer / PerformingRU", _join_unique),
                "Problemsegmente": ("Status", "size"),
                "Regeln": ("Regeln", _join_unique),
                "Meldung": ("Meldung", _join_unique),
                "Begründung": ("Begründung", _join_unique),
                "_first_minute": ("StartMinute", "min"),
                "_last_minute": ("EndMinute", "max"),
            },
        )
        .reset_index()
    )
    grouped["Status"] = grouped["StatusPriorität"].map(_status_from_priority).fillna("Prüfen")
    grouped["Erste Uhrzeit"] = grouped["_first_minute"].map(_minute_to_time)
    grouped["Letzte Uhrzeit"] = grouped["_last_minute"].map(_minute_to_time)
    grouped["Auswahl"] = grouped.apply(
        lambda row: (
            f"{row['Meldetag']} · {row['Loknummer']} · {row['Status']} · "
            f"{int(row['Problemsegmente'])} Segment(e)"
        ),
        axis=1,
    )
    return grouped[REVIEW_QUEUE_COLUMNS].sort_values(
        by=["StatusPriorität", "Meldetag", "Loknummer"],
        ascending=[False, True, True],
        kind="stable",
    ).reset_index(drop=True)
