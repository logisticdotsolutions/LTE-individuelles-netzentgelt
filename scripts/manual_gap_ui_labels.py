from __future__ import annotations

import pandas as pd


NO_LTE_ASSIGNMENT_CODE = "NO_LTE_ASSIGNMENT"
NO_LTE_ASSIGNMENT_LABEL = "Keine LTE-Zuweisung (z. B. Übergabe an anderes EVU)"
GAP_REVIEW_MIN_MINUTES = 120


def clean(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def duration_minutes(start_value: object, end_value: object) -> int | None:
    start = pd.to_datetime(start_value, errors="coerce")
    end = pd.to_datetime(end_value, errors="coerce")
    if pd.isna(start) or pd.isna(end):
        return None
    return max(0, int(round((end - start).total_seconds() / 60.0)))


def duration_label(start_value: object, end_value: object) -> str:
    minutes = duration_minutes(start_value, end_value)
    return f"{minutes} Minuten" if minutes is not None else "Dauer unbekannt"
