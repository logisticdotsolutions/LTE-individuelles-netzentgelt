from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
EXPORT_DIR = DATA_DIR / "03_exports"

OPERATIONAL_DAY_MARKER = "NETZENTGELT_OPERATIONAL_DAY_FILTER_PHASE11G_V1_20260612"
PHASE5C_DAY_FILTER_MARKER = "NETZENTGELT_OPERATIONAL_DAY_FILTER_PHASE5C_V1_20260608"
GAP_OVERLAP_UI_HOTFIX_MARKER = "NETZENTGELT_OPERATIONAL_DAY_FILTER_GAP_OVERLAP_V1_20260609"
GAP_CONTEXT_UI_HOTFIX_MARKER = "NETZENTGELT_OPERATIONAL_DAY_FILTER_GAP_CONTEXT_V1_20260609"
LARGE_GAP_CONTEXT_MINUTES = 480
VIENNA_TIMEZONE = ZoneInfo("Europe/Vienna")
EARLY_RENDER_FLAG = "_operational_day_filter_rendered_early"


def default_operational_day(reference_date: date | None = None) -> date:
    """Return the default completed operational day."""
    base_date = reference_date or datetime.now(VIENNA_TIMEZONE).date()
    return base_date - timedelta(days=2)


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


def _parse_timestamp_series(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce")
    missing = parsed.isna()
    if bool(missing.any()):
        parsed_dayfirst = pd.to_datetime(series[missing], errors="coerce", dayfirst=True)
        parsed.loc[missing] = parsed_dayfirst
    return parsed


def _parse_timestamp_series_utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce", utc=True)


def _coerce_utc(series: pd.Series) -> pd.Series:
    return _parse_timestamp_series_utc(series)


def _coalesced_timestamp_series(data: pd.DataFrame, timestamp_candidates: Iterable[str]) -> tuple[pd.Series, list[str]]:
    result = pd.Series(pd.NaT, index=data.index, dtype="datetime64[ns]")
    used_columns: list[str] = []
    for candidate in timestamp_candidates:
        actual = _column(data, [candidate])
        if not actual or actual in used_columns:
            continue
        used_columns.append(actual)
        parsed = _parse_timestamp_series(data[actual])
        result = result.fillna(parsed)
    return result, used_columns


def _coalesced_timestamp_series_utc(data: pd.DataFrame, timestamp_candidates: Iterable[str]) -> tuple[pd.Series, list[str]]:
    result = pd.Series(pd.NaT, index=data.index, dtype="datetime64[ns, UTC]")
    used_columns: list[str] = []
    for candidate in timestamp_candidates:
        actual = _column(data, [candidate])
        if not actual or actual in used_columns:
            continue
        used_columns.append(actual)
        parsed = _parse_timestamp_series_utc(data[actual])
        result = result.fillna(parsed)
    return result, used_columns


def _date_range_mask(anchor: pd.Series, date_from: date, date_to: date) -> pd.Series:
    start = pd.Timestamp(date_from, tz="UTC")
    end = pd.Timestamp(date_to + timedelta(days=1), tz="UTC")
    return anchor.notna() & anchor.ge(start) & anchor.lt(end)


def _gap_interval_overlap_mask(data: pd.DataFrame, *, date_from: date, date_to: date) -> tuple[pd.Series, pd.Series]:
    normalized_from, normalized_to = normalize_day_range(date_from, date_to)
    starts, start_columns = _coalesced_timestamp_series_utc(data, ["gap_from_utc", "period_start_utc"])
    ends, end_columns = _coalesced_timestamp_series_utc(data, ["gap_to_utc", "period_end_utc"])
    has_interval = starts.notna() & ends.notna()
    if not start_columns or not end_columns:
        return pd.Series(False, index=data.index, dtype=bool), has_interval
    selected_start = pd.Timestamp(normalized_from, tz="UTC")
    selected_end_exclusive = pd.Timestamp(normalized_to + timedelta(days=1), tz="UTC")
    overlaps = has_interval & starts.lt(selected_end_exclusive) & ends.gt(selected_start)
    return overlaps, has_interval


def _truthy_series(series: pd.Series) -> pd.Series:
    return (
        series.fillna("")
        .astype(str)
        .str.strip()
        .str.lower()
        .isin(["true", "1", "yes", "y", "ja"])
    )


def _gap_context_neighbour_mask(data: pd.DataFrame, *, row_type: pd.Series, gap_overlaps: pd.Series) -> pd.Series:
    result = pd.Series(False, index=data.index, dtype=bool)
    loco_column = _column(data, ["loco_no", "LocomotiveNo", "locomotive_no"])
    if not loco_column:
        return result

    gap_starts, gap_start_columns = _coalesced_timestamp_series_utc(data, ["gap_from_utc", "period_start_utc"])
    gap_ends, gap_end_columns = _coalesced_timestamp_series_utc(data, ["gap_to_utc", "period_end_utc"])
    if not gap_start_columns or not gap_end_columns:
        return result

    duration_column = _column(data, ["gap_duration_minutes"])
    if duration_column:
        duration_minutes = pd.to_numeric(data[duration_column], errors="coerce")
    else:
        duration_minutes = (gap_ends - gap_starts).dt.total_seconds() / 60.0

    relevant_gap = (
        row_type.eq("GAP")
        & gap_overlaps
        & gap_starts.notna()
        & gap_ends.notna()
        & duration_minutes.ge(LARGE_GAP_CONTEXT_MINUTES)
    )
    gap_relevance_column = _column(data, ["gap_relevant_de"])
    if gap_relevance_column:
        relevant_gap = relevant_gap & _truthy_series(data[gap_relevance_column])

    if not bool(relevant_gap.any()):
        return result

    movement_mask = row_type.eq("MOVEMENT")
    movement_starts, movement_start_columns = _coalesced_timestamp_series_utc(
        data,
        ["period_start_utc", "actual_departure_ts", "ActualDeparture", "sequence_ts"],
    )
    movement_ends, movement_end_columns = _coalesced_timestamp_series_utc(
        data,
        ["period_end_utc", "actual_arrival_ts", "ActualArrival", "sequence_ts"],
    )
    if not movement_start_columns or not movement_end_columns:
        return result

    loco_values = data[loco_column].fillna("").astype(str).str.strip()
    for gap_index in data.index[relevant_gap]:
        loco_no = loco_values.loc[gap_index]
        if not loco_no:
            continue
        same_loco_movements = movement_mask & loco_values.eq(loco_no)
        previous_candidates = same_loco_movements & movement_ends.le(gap_starts.loc[gap_index])
        following_candidates = same_loco_movements & movement_starts.ge(gap_ends.loc[gap_index])
        if bool(previous_candidates.any()):
            result.loc[movement_ends[previous_candidates].idxmax()] = True
        if bool(following_candidates.any()):
            result.loc[movement_starts[following_candidates].idxmin()] = True
    return result


def filter_by_operational_days(
    data: pd.DataFrame,
    *,
    date_from: date,
    date_to: date,
    timestamp_candidates: Iterable[str],
    keep_rows_without_timestamp: bool = False,
) -> pd.DataFrame:
    """Filter UI data by full operational calendar days, with GAP interval handling."""
    if data is None:
        return pd.DataFrame()
    if data.empty:
        return data.copy()

    normalized_from, normalized_to = normalize_day_range(date_from, date_to)
    timestamps, used_columns = _coalesced_timestamp_series(data, timestamp_candidates)
    if not used_columns:
        return data.copy()

    day_values = timestamps.dt.date
    mask = day_values.notna() & (day_values >= normalized_from) & (day_values <= normalized_to)
    if keep_rows_without_timestamp:
        mask = mask | day_values.isna()

    row_type_column = _column(data, ["row_type"])
    if row_type_column:
        row_type = data[row_type_column].fillna("").astype(str).str.strip().str.upper()
        is_gap = row_type.eq("GAP")
        gap_overlaps, gap_has_interval = _gap_interval_overlap_mask(
            data,
            date_from=normalized_from,
            date_to=normalized_to,
        )
        mask = (~is_gap & mask) | (is_gap & (gap_overlaps | (~gap_has_interval & mask)))
        mask = mask | _gap_context_neighbour_mask(data, row_type=row_type, gap_overlaps=gap_overlaps)

    return data.loc[mask].copy()


def filter_dataframe_by_operational_day(
    df: pd.DataFrame,
    *,
    date_from: date,
    date_to: date,
    time_columns: Iterable[str],
) -> pd.DataFrame:
    """Compatibility wrapper for older callers."""
    return filter_by_operational_days(
        df,
        date_from=date_from,
        date_to=date_to,
        timestamp_candidates=time_columns,
    )


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
        filtered = filter_by_operational_days(
            df,
            date_from=normalized_from,
            date_to=normalized_to,
            timestamp_candidates=time_columns,
        )
        _write_csv(filtered, path)
        result[filename] = int(len(filtered))
    return result


def summarize_no_loco_cases(cases: pd.DataFrame, fallback_summary: pd.DataFrame) -> pd.DataFrame:
    """Recalculate the technical R012 raw-data overview for the selected day."""
    expected_columns = ["Quelle", "Prüfung", "Anzahl Zeilen", "Betroffene Transporte", "Status"]
    if fallback_summary is None or fallback_summary.empty:
        base = pd.DataFrame(columns=expected_columns)
    else:
        base = fallback_summary.copy()
        for column in expected_columns:
            if column not in base.columns:
                base[column] = ""
        base = base[expected_columns]

    if cases is None or cases.empty:
        if base.empty:
            return base
        result = base.copy()
        result["Anzahl Zeilen"] = 0
        result["Betroffene Transporte"] = 0
        return result

    work = cases.copy()
    if "Quelle" not in work.columns:
        return base
    if "Anzahl Zeilen" not in work.columns:
        work["Anzahl Zeilen"] = 1
    work["Anzahl Zeilen"] = pd.to_numeric(work["Anzahl Zeilen"], errors="coerce").fillna(0).astype(int)

    grouped = (
        work.groupby("Quelle", dropna=False)
        .agg(
            **{
                "Anzahl Zeilen": ("Anzahl Zeilen", "sum"),
                "Betroffene Transporte": ("TransportNumber", "nunique")
                if "TransportNumber" in work.columns
                else ("Quelle", "size"),
            }
        )
        .reset_index()
    )

    if base.empty:
        grouped["Prüfung"] = "Gefilterte technische R012-Rohdatenprüfung"
        grouped["Status"] = "OK"
        return grouped[expected_columns]

    result = base.drop(columns=["Anzahl Zeilen", "Betroffene Transporte"], errors="ignore").merge(
        grouped,
        on="Quelle",
        how="left",
    )
    result["Anzahl Zeilen"] = pd.to_numeric(result["Anzahl Zeilen"], errors="coerce").fillna(0).astype(int)
    result["Betroffene Transporte"] = pd.to_numeric(
        result["Betroffene Transporte"], errors="coerce"
    ).fillna(0).astype(int)
    return result[expected_columns]


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
    """Render the unified UI day filter in the sidebar."""
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
