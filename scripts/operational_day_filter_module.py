"""
Netzentgelt MVP - zentraler Filter fuer operative Kalendertage
=============================================================

Der Filter gilt ausschliesslich fuer UI-Ansichten. Die fachliche Pipeline,
DuckDB-Tabellen und Exporte bleiben unveraendert. Standardmaessig wird der
vollstaendige vorgestrige Kalendertag angezeigt. Uhrzeiten werden bei der
Filterung bewusst ignoriert.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Iterable

import pandas as pd


PHASE5C_DAY_FILTER_MARKER = "NETZENTGELT_OPERATIONAL_DAY_FILTER_PHASE5C_V1_20260608"
GAP_OVERLAP_UI_HOTFIX_MARKER = "NETZENTGELT_OPERATIONAL_DAY_FILTER_GAP_OVERLAP_V1_20260609"
VIENNA_TIMEZONE = ZoneInfo("Europe/Vienna")


def default_operational_day(reference_date: date | None = None) -> date:
    """Vollstaendigen vorgestrigen Kalendertag liefern."""
    base_date = reference_date or datetime.now(VIENNA_TIMEZONE).date()
    return base_date - timedelta(days=2)


def normalize_day_range(date_from: date, date_to: date) -> tuple[date, date]:
    """Reihenfolge defensiv normalisieren, damit die Anzeige nicht abbricht."""
    return (date_from, date_to) if date_from <= date_to else (date_to, date_from)


def _column(data: pd.DataFrame, candidates: Iterable[str]) -> str | None:
    by_lower = {str(column).lower(): str(column) for column in data.columns}
    for candidate in candidates:
        actual = by_lower.get(str(candidate).lower())
        if actual:
            return actual
    return None


def _parse_timestamp_series(series: pd.Series) -> pd.Series:
    """ISO- und deutsch formatierte Zeitwerte robust als Timestamp lesen."""
    parsed = pd.to_datetime(series, errors="coerce")
    missing = parsed.isna()
    if bool(missing.any()):
        parsed_dayfirst = pd.to_datetime(series[missing], errors="coerce", dayfirst=True)
        parsed.loc[missing] = parsed_dayfirst
    return parsed


def _parse_timestamp_series_utc(series: pd.Series) -> pd.Series:
    """Zeitwerte fuer robuste Intervallvergleiche einheitlich in UTC lesen."""
    return pd.to_datetime(series, errors="coerce", utc=True)


def _coalesced_timestamp_series(
    data: pd.DataFrame,
    timestamp_candidates: Iterable[str],
) -> tuple[pd.Series, list[str]]:
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


def _coalesced_timestamp_series_utc(
    data: pd.DataFrame,
    timestamp_candidates: Iterable[str],
) -> tuple[pd.Series, list[str]]:
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


def _gap_interval_overlap_mask(
    data: pd.DataFrame,
    *,
    date_from: date,
    date_to: date,
) -> tuple[pd.Series, pd.Series]:
    """
    Relevante GAP-Zeilen nach Intervallueberschneidung mit dem Arbeitszeitraum filtern.

    Eine mehrtaegige GAP muss an jedem betroffenen Kalendertag sichtbar bleiben,
    weil das Quality Gate ihre 15-Minuten-Slots ebenfalls tagesweise bewertet.
    """
    normalized_from, normalized_to = normalize_day_range(date_from, date_to)
    starts, start_columns = _coalesced_timestamp_series_utc(
        data,
        ["gap_from_utc", "period_start_utc"],
    )
    ends, end_columns = _coalesced_timestamp_series_utc(
        data,
        ["gap_to_utc", "period_end_utc"],
    )
    has_interval = starts.notna() & ends.notna()
    if not start_columns or not end_columns:
        return pd.Series(False, index=data.index, dtype=bool), has_interval

    selected_start = pd.Timestamp(normalized_from, tz="UTC")
    selected_end_exclusive = pd.Timestamp(normalized_to + timedelta(days=1), tz="UTC")
    overlaps = (
        has_interval
        & starts.lt(selected_end_exclusive)
        & ends.gt(selected_start)
    )
    return overlaps, has_interval


def filter_by_operational_days(
    data: pd.DataFrame,
    *,
    date_from: date,
    date_to: date,
    timestamp_candidates: Iterable[str],
    keep_rows_without_timestamp: bool = False,
) -> pd.DataFrame:
    """
    UI-Daten auf vollstaendige Kalendertage einschraenken.

    Die Uhrzeit wird ignoriert. Technisch entspricht dies je gewaehltem Bereich
    [Von-Tag 00:00, Tag nach Bis-Tag 00:00). Bei gemischten Tabellen wird der
    erste auswertbare Zeitwert aus der Kandidatenliste verwendet.

    Ausnahme fuer Timeline- und Finding-GAPs:
    Sobald row_type = GAP und belastbare Intervallgrenzen vorliegen, gilt eine
    Zeile fuer jeden operativen Tag als sichtbar, den ihr Zeitraum schneidet.
    Normale Bewegungen bleiben weiterhin am ersten auswertbaren Zeitanker und
    damit insbesondere an ActualDeparture ausgerichtet.
    """
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
        mask = (
            (~is_gap & mask)
            | (
                is_gap
                & (
                    gap_overlaps
                    | (~gap_has_interval & mask)
                )
            )
        )

    return data.loc[mask].copy()


def summarize_no_loco_cases(
    cases: pd.DataFrame,
    fallback_summary: pd.DataFrame,
) -> pd.DataFrame:
    """Technische R012-Rohdatenuebersicht passend zum gewaehlten Tag neu zaehlen."""
    expected_columns = ["Quelle", "Pruefung", "Anzahl Zeilen", "Betroffene Transporte", "Status"]
    # Bestehende App verwendet Umlaute in der Spaltenbezeichnung.
    expected_columns[1] = "Prüfung"

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
        grouped["Prüfung"] = "Gefilterte technische R012-Rohdatenpruefung"
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


def render_sidebar_operational_day_filter() -> tuple[date, date]:
    """Einheitlichen UI-Filter in der Seitenleiste rendern."""
    import streamlit as st

    default_day = default_operational_day()
    st.sidebar.divider()
    st.sidebar.header("Arbeitszeitraum")
    st.sidebar.caption(
        "Der Filter gilt zentral fuer Tagespruefung, Prueffaelle, Lok-Detailpruefung, "
        "Fallbearbeitung und Systemvorschlaege. Movements richten sich nach ActualDeparture. "
        "GAPs bleiben an jedem geschnittenen Kalendertag sichtbar. "
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
