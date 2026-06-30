from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Iterable

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
EXPORT_DIR = DATA_DIR / "03_exports"

OPERATIONAL_DAY_MARKER = "NETZENTGELT_OPERATIONAL_DAY_FILTER_PHASE11G_V1_20260612"
EARLY_RENDER_FLAG = "_operational_day_filter_rendered_early"


def default_operational_day() -> date:
    """Return a deterministic default day for operational filtering."""
    return date.today()


def normalize_day_range(date_from: date, date_to: date) -> tuple[date, date]:
    """Return the day range in ascending order."""
    return (date_from, date_to) if date_from <= date_to else (date_to, date_from)


def _read_csv_safe(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path, sep=None, engine="python", encoding="utf-8-sig")
    except Exception:
        try:
            return pd.read_csv(path, sep=";", encoding="utf-8-sig")
        except Exception:
            return pd.DataFrame()


def _write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, sep=";", index=False, encoding="utf-8-sig")


def _column(df: pd.DataFrame, candidates: Iterable[str]) -> str | None:
    if df.empty:
        return None
    lower_map = {str(column).lower(): str(column) for column in df.columns}
    for candidate in candidates:
        actual = lower_map.get(str(candidate).lower())
        if actual:
            return actual
    return None


def _coerce_utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce", utc=True)


def _date_range_mask(anchor: pd.Series, date_from: date, date_to: date) -> pd.Series:
    start = pd.Timestamp(date_from, tz="UTC")
    end = pd.Timestamp(date_to + timedelta(days=1), tz="UTC")
    return anchor.notna() & anchor.ge(start) & anchor.lt(end)


def filter_dataframe_by_operational_day(
    df: pd.DataFrame,
    *,
    date_from: date,
    date_to: date,
    time_columns: Iterable[str],
) -> pd.DataFrame:
    """Filter a dataframe by the first available timestamp column."""
    if df.empty:
        return df.copy()
    normalized_from, normalized_to = normalize_day_range(date_from, date_to)
    for column in time_columns:
        actual = _column(df, [column])
        if actual:
            anchor = _coerce_utc(df[actual])
            return df.loc[_date_range_mask(anchor, normalized_from, normalized_to)].copy()
    return df.copy()


def apply_operational_day_filter_to_exports(
    *,
    date_from: date,
    date_to: date,
    export_dir: Path = EXPORT_DIR,
) -> dict[str, int]:
    """Filter selected export files by operational day after the pipeline created them."""
    normalized_from, normalized_to = normalize_day_range(date_from, date_to)
    specs = {
        "core_loco_timeline.csv": ["period_start_utc", "actual_departure_ts", "sequence_ts"],
        "dq_findings.csv": ["period_start_utc", "actual_departure_ts", "sequence_ts"],
        "dq_export_gate.csv": ["period_start_utc", "actual_departure_ts", "sequence_ts"],
        "dq_export_gate_ru.csv": ["period_start_utc", "actual_departure_ts", "sequence_ts"],
        "dq_global_export_blockers.csv": ["period_start_utc", "actual_departure_ts", "sequence_ts"],
        "export_excluded_rows.csv": ["period_start_utc", "actual_departure_ts", "sequence_ts"],
    }
    result: dict[str, int] = {}
    for filename, time_columns in specs.items():
        path = export_dir / filename
        df = _read_csv_safe(path)
        if df.empty:
            result[filename] = 0
            continue
        filtered = filter_dataframe_by_operational_day(
            df,
            date_from=normalized_from,
            date_to=normalized_to,
            time_columns=time_columns,
        )
        _write_csv(filtered, path)
        result[filename] = int(len(filtered))
    return result


def _selected_range_from_session_state(st_module) -> tuple[date, date]:
    fallback = default_operational_day()
    date_from = st_module.session_state.get("operational_day_filter_from", fallback)
    date_to = st_module.session_state.get("operational_day_filter_to", date_from)
    if not isinstance(date_from, date):
        date_from = fallback
    if not isinstance(date_to, date):
        date_to = date_from
    return normalize_day_range(date_from, date_to)


def render_sidebar_operational_day_filter() -> tuple[date, date]:
    """Einheitlichen UI-Filter in der Seitenleiste rendern."""
    import streamlit as st

    if bool(st.session_state.get(EARLY_RENDER_FLAG, False)):
        normalized_from, normalized_to = _selected_range_from_session_state(st)
        st.sidebar.info(
            f"Arbeitszeitraum aktiv: {normalized_from:%d.%m.%Y} 00:00 bis "
            f"{(normalized_to + timedelta(days=1)):%d.%m.%Y} 00:00."
        )
        return normalized_from, normalized_to

    default_day = default_operational_day()
    st.sidebar.divider()
    st.sidebar.header("Arbeitszeitraum")
    st.sidebar.caption(
        "Der Filter gilt zentral fuer Tagespruefung, Prueffaelle, Lok-Detailpruefung, "
        "Fallbearbeitung und Systemvorschlaege. Movements richten sich nach ActualDeparture. "
        "GAPs bleiben an jedem geschnittenen Kalendertag sichtbar. Bei GAPs ueber acht Stunden "
        "werden die direkt angrenzenden Bewegungen als Kontext eingeblendet. "
        "Es werden immer vollstaendige Kalendertage betrachtet; Uhrzeiten werden ignoriert."
    )
    date_from = st.sidebar.date_input(
        "Von-Tag",
        value=default_day,
        key="operational_day_filter_from",
    )
    date_to = st.sidebar.date_input(
        "Bis-Tag",
        value=default_day,
        key="operational_day_filter_to",
    )
    normalized_from, normalized_to = normalize_day_range(date_from, date_to)
    if (date_from, date_to) != (normalized_from, normalized_to):
        st.sidebar.warning("Von- und Bis-Tag wurden fuer die Anzeige automatisch sortiert.")
    st.sidebar.info(
        f"Aktiv: {normalized_from:%d.%m.%Y} 00:00 bis "
        f"{(normalized_to + timedelta(days=1)):%d.%m.%Y} 00:00."
    )
    return normalized_from, normalized_to
