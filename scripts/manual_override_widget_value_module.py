"""Pure helper functions for consistent correction widget values."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Iterable

import pandas as pd


GUIDED_WIDGET_VALUE_MARKER = "NETZENTGELT_GUIDED_WIDGET_VALUES_PHASE9D_V1_20260610"
PERFORMING_RU_COLUMNS = ("performing_ru", "PerformingRU", "CurrentContractant")
EMPTY_DROPDOWN_VALUE = "— Bitte auswählen —"


def _clean(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _pick_column(columns: Iterable[object], candidates: Iterable[str]) -> str | None:
    by_lower = {str(column).lower(): str(column) for column in columns}
    for candidate in candidates:
        actual = by_lower.get(candidate.lower())
        if actual:
            return actual
    return None


def performing_ru_options(
    timeline: pd.DataFrame | None,
    *,
    current_value: object = "",
    suggested_value: object = "",
) -> tuple[str, ...]:
    """Return stable dropdown options without free-text variants."""
    values: set[str] = set()
    if isinstance(timeline, pd.DataFrame) and not timeline.empty:
        column = _pick_column(timeline.columns, PERFORMING_RU_COLUMNS)
        if column:
            values.update(_clean(value) for value in timeline[column].tolist() if _clean(value))
    for value in (current_value, suggested_value):
        cleaned = _clean(value)
        if cleaned and " | " not in cleaned and "…" not in cleaned:
            values.add(cleaned)
    return (EMPTY_DROPDOWN_VALUE, *tuple(sorted(values, key=str.casefold)))


def parse_utc_picker_default(value: object) -> datetime | None:
    """Parse an existing technical value for date/time picker defaults."""
    cleaned = _clean(value)
    if not cleaned:
        return None
    parsed = pd.to_datetime(cleaned, errors="coerce", utc=True)
    if pd.isna(parsed):
        return None
    return pd.Timestamp(parsed).to_pydatetime().replace(tzinfo=None)


def combine_utc_picker_value(day: date | None, clock: time | None) -> str:
    """Return one strict UTC timestamp string from picker values."""
    if day is None or clock is None:
        return ""
    return datetime.combine(day, clock).strftime("%Y-%m-%d %H:%M:%S")
