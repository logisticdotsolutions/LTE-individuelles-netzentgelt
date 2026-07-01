from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Iterable, Sequence

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
EXPORT_DIR = ROOT / "data" / "03_exports"
TIMELINE_PATH = EXPORT_DIR / "core_loco_timeline.csv"
WATERFALL_TAB_LABEL = "5. Wasserfall"
LOCO_TAB_LABEL = "4. Lok prüfen"
EXPORT_TAB_LABEL = "5. Exporte erstellen"
EXPORT_TAB_RENUMBERED_LABEL = "6. Exporte erstellen"
TECH_TAB_LABEL = "⚙️ Technik"
WATERFALL_OVERVIEW_MARKER = "NETZENTGELT_WATERFALL_OVERVIEW_PHASE14C_V1_20260629"


LOCO_COLUMNS = ["loco_no", "LocomotiveNo", "locomotive_no", "Loknummer"]
HOLDER_COLUMNS = ["holder_name", "Holder", "holder", "Halter"]
PERFORMING_RU_COLUMNS = ["performing_ru", "PerformingRU", "current_contractant", "CurrentContractant"]
TRANSPORT_COLUMNS = ["transport_number", "TransportNumber", "TransportNo"]
ROUTE_TYPE_COLUMNS = ["cal_route_type_home", "Route Type", "route_type"]
EVENT_LABEL_COLUMNS = ["de_event_label", "Event Type"]
START_TIME_COLUMNS = ["period_start_utc", "actual_departure_ts", "ActualDeparture", "sequence_ts"]
END_TIME_COLUMNS = ["period_end_utc", "actual_arrival_ts", "ActualArrival", "sequence_ts"]


DE_EVENT_LABELS = {
    "IN DE",
    "EINFAHRT",
    "AUSFAHRT",
    "EINFAHRT + AUSFAHRT",
}


DETAIL_COLUMNS = [
    "Loknummer",
    "Halter",
    "PerformingRU",
    "Zeitraum von",
    "Zeitraum bis",
    "Bewegungen",
    "Transporte",
    "Gefahrene Tage",
    "Tage",
    "Route Type",
    "Einfahrten",
    "Ausfahrten",
]


EMPTY_OVERVIEW = pd.DataFrame(columns=DETAIL_COLUMNS)


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


def _column(source_df: pd.DataFrame, candidates: Iterable[str]) -> str | None:
    if source_df.empty:
        return None
    by_lower = {str(column).lower(): str(column) for column in source_df.columns}
    for candidate in candidates:
        actual = by_lower.get(str(candidate).lower())
        if actual:
            return actual
    return None


def _text_series(source_df: pd.DataFrame, column: str | None, fallback: str = "") -> pd.Series:
    if not column or column not in source_df.columns:
        return pd.Series(fallback, index=source_df.index, dtype="object")
    return source_df[column].fillna("").astype(str).str.strip()


def _coalesced_timestamp(source_df: pd.DataFrame, candidates: Iterable[str]) -> pd.Series:
    result = pd.Series(pd.NaT, index=source_df.index, dtype="datetime64[ns, UTC]")
    for candidate in candidates:
        column = _column(source_df, [candidate])
        if not column:
            continue
        parsed = pd.to_datetime(source_df[column], errors="coerce", utc=True)
        result = result.fillna(parsed)
    return result


def _date_range_mask(anchor: pd.Series, date_from: date, date_to: date) -> pd.Series:
    start = pd.Timestamp(min(date_from, date_to), tz="UTC")
    end = pd.Timestamp(max(date_from, date_to) + timedelta(days=1), tz="UTC")
    return anchor.notna() & anchor.ge(start) & anchor.lt(end)


def _join_unique(values: pd.Series) -> str:
    cleaned = sorted({str(value).strip() for value in values.dropna().tolist() if str(value).strip()})
    return " | ".join(cleaned)


def _format_timestamp(value: object) -> str:
    if pd.isna(value):
        return ""
    return pd.Timestamp(value).strftime("%d.%m.%Y %H:%M")


def _format_day_list(values: pd.Series) -> str:
    days = sorted({value for value in values.dropna().tolist() if value})
    if not days:
        return ""
    if len(days) > 7:
        return f"{len(days)} Tage"
    return ", ".join(pd.Timestamp(day).strftime("%d.%m.%Y") for day in days)


def _build_de_relevance_mask(source_df: pd.DataFrame) -> pd.Series:
    report_scope_col = _column(source_df, ["report_scope"])
    event_label_col = _column(source_df, EVENT_LABEL_COLUMNS)
    route_type_col = _column(source_df, ROUTE_TYPE_COLUMNS)

    masks: list[pd.Series] = []
    if report_scope_col:
        masks.append(_text_series(source_df, report_scope_col).str.upper().eq("IN_REPORT"))
    if event_label_col:
        masks.append(_text_series(source_df, event_label_col).str.upper().isin(DE_EVENT_LABELS))
    if route_type_col:
        route_values = _text_series(source_df, route_type_col).str.casefold()
        masks.append(route_values.ne("") & ~route_values.eq("kein bezug"))

    if not masks:
        return pd.Series(True, index=source_df.index, dtype=bool)

    result = masks[0]
    for mask in masks[1:]:
        result = result | mask
    return result


def build_waterfall_loco_overview(
    source_df: pd.DataFrame,
    *,
    date_from: date,
    date_to: date,
) -> pd.DataFrame:
    """Create a gap-free DE locomotive overview for the selected operational day range."""
    if source_df.empty:
        return EMPTY_OVERVIEW.copy()

    work = source_df.copy()
    row_type_col = _column(work, ["row_type"])
    if row_type_col:
        work = work[_text_series(work, row_type_col).str.upper().eq("MOVEMENT")].copy()

    if work.empty:
        return EMPTY_OVERVIEW.copy()

    anchor_ts = _coalesced_timestamp(work, START_TIME_COLUMNS)
    work = work.loc[_date_range_mask(anchor_ts, date_from, date_to)].copy()
    anchor_ts = anchor_ts.loc[work.index]
    if work.empty:
        return EMPTY_OVERVIEW.copy()

    work = work.loc[_build_de_relevance_mask(work)].copy()
    anchor_ts = anchor_ts.loc[work.index]
    if work.empty:
        return EMPTY_OVERVIEW.copy()

    loco_col = _column(work, LOCO_COLUMNS)
    if not loco_col:
        return EMPTY_OVERVIEW.copy()

    holder_col = _column(work, HOLDER_COLUMNS)
    performing_col = _column(work, PERFORMING_RU_COLUMNS)
    transport_col = _column(work, TRANSPORT_COLUMNS)
    route_type_col = _column(work, ROUTE_TYPE_COLUMNS)
    event_label_col = _column(work, EVENT_LABEL_COLUMNS)

    work["_loco"] = _text_series(work, loco_col)
    work = work[work["_loco"].ne("") & work["_loco"].ne("00000000000-0")].copy()
    anchor_ts = anchor_ts.loc[work.index]
    if work.empty:
        return EMPTY_OVERVIEW.copy()

    end_ts = _coalesced_timestamp(work, END_TIME_COLUMNS).fillna(anchor_ts)
    work["_holder"] = _text_series(work, holder_col, fallback="(Halter fehlt)").replace("", "(Halter fehlt)")
    work["_performing_ru"] = _text_series(work, performing_col, fallback="(PerformingRU fehlt)").replace("", "(PerformingRU fehlt)")
    work["_transport"] = _text_series(work, transport_col)
    work["_route_type"] = _text_series(work, route_type_col)
    work["_event_label"] = _text_series(work, event_label_col).str.upper()
    work["_anchor_ts"] = anchor_ts
    work["_end_ts"] = end_ts
    work["_anchor_day"] = work["_anchor_ts"].dt.date

    grouped = (
        work.groupby(["_loco", "_holder", "_performing_ru"], dropna=False)
        .agg(
            first_ts=("_anchor_ts", "min"),
            last_ts=("_end_ts", "max"),
            movement_count=("_loco", "size"),
            transport_count=("_transport", lambda values: len({value for value in values if value})),
            day_count=("_anchor_day", lambda values: len({value for value in values.dropna()})),
            day_list=("_anchor_day", _format_day_list),
            route_types=("_route_type", _join_unique),
            entry_count=("_event_label", lambda values: int(values.str.contains("EINFAHRT", na=False).sum())),
            exit_count=("_event_label", lambda values: int(values.str.contains("AUSFAHRT", na=False).sum())),
        )
        .reset_index()
    )

    result = grouped.rename(
        columns={
            "_loco": "Loknummer",
            "_holder": "Halter",
            "_performing_ru": "PerformingRU",
            "movement_count": "Bewegungen",
            "transport_count": "Transporte",
            "day_count": "Gefahrene Tage",
            "day_list": "Tage",
            "route_types": "Route Type",
            "entry_count": "Einfahrten",
            "exit_count": "Ausfahrten",
        }
    )
    result["Zeitraum von"] = result["first_ts"].map(_format_timestamp)
    result["Zeitraum bis"] = result["last_ts"].map(_format_timestamp)

    result = result[DETAIL_COLUMNS].sort_values(
        by=["Loknummer", "Halter", "PerformingRU"],
        ascending=True,
        kind="stable",
    )
    return result.reset_index(drop=True)


def filter_waterfall_overview(
    overview_df: pd.DataFrame,
    *,
    holder: str = "Alle",
    performing_ru: str = "Alle",
    route_type: str = "Alle",
    loco_query: str = "",
) -> pd.DataFrame:
    """Apply the user-facing filters of the waterfall tab to the aggregated overview."""
    if overview_df.empty:
        return overview_df.copy()

    filtered = overview_df.copy()
    if holder != "Alle" and "Halter" in filtered.columns:
        filtered = filtered[filtered["Halter"].astype(str).eq(holder)].copy()
    if performing_ru != "Alle" and "PerformingRU" in filtered.columns:
        filtered = filtered[filtered["PerformingRU"].astype(str).eq(performing_ru)].copy()
    if route_type != "Alle" and "Route Type" in filtered.columns:
        filtered = filtered[
            filtered["Route Type"].astype(str).apply(
                lambda value: route_type in {item.strip() for item in value.split(" | ") if item.strip()}
            )
        ].copy()
    query = loco_query.strip().casefold()
    if query and "Loknummer" in filtered.columns:
        filtered = filtered[filtered["Loknummer"].astype(str).str.casefold().str.contains(query, na=False)].copy()
    return filtered.reset_index(drop=True)


def _options(source_df: pd.DataFrame, column: str) -> list[str]:
    if source_df.empty or column not in source_df.columns:
        return []
    values: set[str] = set()
    for raw_value in source_df[column].dropna().astype(str):
        for value in raw_value.split(" | "):
            cleaned = value.strip()
            if cleaned:
                values.add(cleaned)
    return sorted(values)


def _coerce_selectbox_state(
    session_state: object,
    key: str,
    options: Sequence[object],
    *,
    default: object = "Alle",
) -> int:
    values = list(options)
    if not values:
        return 0

    fallback = default if default in values else values[0]
    current = session_state.get(key, fallback)
    if current not in values:
        session_state[key] = fallback
        current = fallback
    return values.index(current)


def _selectbox_index_for_state(key: str, options: Sequence[object], *, default: object = "Alle") -> int:
    import streamlit as st

    return _coerce_selectbox_state(st.session_state, key, options, default=default)


def _get_selected_day_range() -> tuple[date, date]:
    import streamlit as st

    try:
        import operational_day_filter_module as operational_day_filter
    except Exception:
        operational_day_filter = None

    fallback = date.today()
    date_from = st.session_state.get("operational_day_filter_from", fallback)
    date_to = st.session_state.get("operational_day_filter_to", date_from)

    if not isinstance(date_from, date):
        date_from = fallback
    if not isinstance(date_to, date):
        date_to = date_from

    if operational_day_filter is not None:
        return operational_day_filter.normalize_day_range(date_from, date_to)
    return (date_from, date_to) if date_from <= date_to else (date_to, date_from)


def render_waterfall_overview() -> None:
    """Render the additional gap-free locomotive overview tab."""
    import streamlit as st

    st.header("🌊 Wasserfall: Loks im DE-Zeitraum")
    st.caption(
        "Gap-Zeilen werden bewusst ausgeblendet. Die Liste zeigt alle Loknummern, "
        "die im aktiven Arbeitszeitraum DE-relevante Bewegungen haben — mit Halter "
        "und PerformingRU."
    )

    date_from, date_to = _get_selected_day_range()
    st.info(
        f"Aktiver Arbeitszeitraum: {date_from:%d.%m.%Y} bis {date_to:%d.%m.%Y}. "
        "Der zentrale Sidebar-Filter wird übernommen."
    )

    source_df = _read_csv_safe(TIMELINE_PATH)
    if source_df.empty:
        st.warning("Keine core_loco_timeline.csv gefunden. Bitte zuerst die Tagesprüfung ausführen.")
        return

    overview = build_waterfall_loco_overview(source_df, date_from=date_from, date_to=date_to)
    if overview.empty:
        st.info("Im gewählten Zeitraum wurden keine DE-relevanten Lokbewegungen gefunden.")
        return

    metric_1, metric_2, metric_3, metric_4 = st.columns(4)
    with metric_1:
        st.metric("Loks", int(overview["Loknummer"].nunique()))
    with metric_2:
        st.metric("Bewegungen", int(overview["Bewegungen"].sum()))
    with metric_3:
        st.metric("Halter", int(overview["Halter"].nunique()))
    with metric_4:
        st.metric("PerformingRUs", int(overview["PerformingRU"].nunique()))

    st.markdown("#### Filter")
    filter_1, filter_2, filter_3, filter_4 = st.columns(4)
    with filter_1:
        holder_options = ["Alle"] + _options(overview, "Halter")
        selected_holder = st.selectbox(
            "Halter",
            holder_options,
            index=_selectbox_index_for_state("waterfall_holder", holder_options),
            key="waterfall_holder",
        )
    with filter_2:
        performing_ru_options = ["Alle"] + _options(overview, "PerformingRU")
        selected_performing_ru = st.selectbox(
            "PerformingRU",
            performing_ru_options,
            index=_selectbox_index_for_state("waterfall_performing_ru", performing_ru_options),
            key="waterfall_performing_ru",
        )
    with filter_3:
        route_type_options = ["Alle"] + _options(overview, "Route Type")
        selected_route_type = st.selectbox(
            "Route Type",
            route_type_options,
            index=_selectbox_index_for_state("waterfall_route_type", route_type_options),
            key="waterfall_route_type",
        )
    with filter_4:
        loco_query = st.text_input("Loknummer enthält", key="waterfall_loco_query")

    filtered = filter_waterfall_overview(
        overview,
        holder=selected_holder,
        performing_ru=selected_performing_ru,
        route_type=selected_route_type,
        loco_query=loco_query,
    )

    st.write(f"Angezeigte Kombinationen: **{len(filtered)}**")
    st.dataframe(filtered, use_container_width=True, hide_index=True, height=520)

    csv = filtered.to_csv(index=False, sep=";").encode("utf-8-sig")
    st.download_button(
        "Wasserfall-Liste herunterladen",
        data=csv,
        file_name=f"wasserfall_lokliste_{date_from.isoformat()}_bis_{date_to.isoformat()}.csv",
        mime="text/csv",
        key="download_waterfall_loco_overview",
        use_container_width=True,
    )


def _visible_tab_labels(labels: Sequence[object]) -> tuple[list[object], int | None]:
    values = [str(label) for label in labels]
    if WATERFALL_TAB_LABEL in values or LOCO_TAB_LABEL not in values or EXPORT_TAB_LABEL not in values:
        return list(labels), None

    visible_labels = list(labels)
    export_index = values.index(EXPORT_TAB_LABEL)
    visible_labels[export_index] = EXPORT_TAB_RENUMBERED_LABEL
    waterfall_index = values.index(LOCO_TAB_LABEL) + 1
    visible_labels.insert(waterfall_index, WATERFALL_TAB_LABEL)
    return visible_labels, waterfall_index


def install_waterfall_overview_runtime():
    """Add a gap-free DE locomotive overview tab without changing the legacy app contract."""
    import streamlit as st

    original_tabs = st.tabs
    if getattr(original_tabs, "_waterfall_overview_installed", False):
        return original_tabs

    def patched_tabs(labels: Sequence[object], *args, **kwargs):
        visible_labels, waterfall_index = _visible_tab_labels(labels)
        if waterfall_index is None:
            return original_tabs(labels, *args, **kwargs)

        rendered_tabs = list(original_tabs(visible_labels, *args, **kwargs))
        if 0 <= waterfall_index < len(rendered_tabs):
            with rendered_tabs[waterfall_index]:
                render_waterfall_overview()
            return rendered_tabs[:waterfall_index] + rendered_tabs[waterfall_index + 1:]
        return rendered_tabs

    patched_tabs._waterfall_overview_installed = True
    st.tabs = patched_tabs
    return original_tabs


def restore_waterfall_overview_runtime(original_tabs) -> None:
    if original_tabs is None:
        return
    import streamlit as st

    st.tabs = original_tabs
