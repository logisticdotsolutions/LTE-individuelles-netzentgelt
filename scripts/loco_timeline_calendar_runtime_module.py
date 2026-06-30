from __future__ import annotations

from datetime import date, timedelta
from html import escape
from io import BytesIO
from pathlib import Path
from typing import Iterable, Sequence

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
EXPORT_DIR = ROOT / "data" / "03_exports"
TIMELINE_PATH = EXPORT_DIR / "core_loco_timeline.csv"

WATERFALL_TAB_LABEL = "5. Wasserfall"
LOCO_TAB_LABEL = "4. Lok prüfen"
TIMELINE_TAB_LABEL = "6. Lok-Zeitachse"
TIMELINE_TAB_LABEL_WITHOUT_WATERFALL = "5. Lok-Zeitachse"
EXPORT_TAB_LABELS = ["5. Exporte erstellen", "6. Exporte erstellen"]
EXPORT_TAB_RENUMBERED_LABEL = "7. Exporte erstellen"

LOCO_COLUMNS = ["loco_no", "LocomotiveNo", "locomotive_no", "Loknummer"]
HOLDER_COLUMNS = ["holder_name", "Holder", "holder", "Halter"]
PERFORMING_RU_COLUMNS = [
    "performing_ru",
    "PerformingRU",
    "current_contractant",
    "CurrentContractant",
]
ROUTE_TYPE_COLUMNS = ["cal_route_type_home", "Route Type", "route_type"]
EVENT_LABEL_COLUMNS = ["de_event_label", "Event Type"]
ROW_TYPE_COLUMNS = ["row_type", "RowType"]
MESSAGE_COLUMNS = ["dq_messages", "Error Message", "error_message"]
RULE_COLUMNS = ["dq_rule_ids", "RuleIds", "rule_ids"]
DECISION_COLUMNS = ["decision_reason", "Begründung", "DecisionReason"]
TRANSPORT_COLUMNS = ["transport_number", "TransportNumber", "TransportNo"]
START_TIME_COLUMNS = [
    "period_start_utc",
    "actual_departure_ts",
    "ActualDeparture",
    "sequence_ts",
]
END_TIME_COLUMNS = [
    "period_end_utc",
    "actual_arrival_ts",
    "ActualArrival",
    "sequence_ts",
]

DE_EVENT_LABELS = {
    "IN DE",
    "EINFAHRT",
    "AUSFAHRT",
    "EINFAHRT + AUSFAHRT",
}
DE_ROUTE_KEYWORDS = (
    "inland",
    "einfahrt",
    "ausfahrt",
    "passiert",
    "komplex",
    "in de",
)
NON_DE_KEYWORDS = (
    "außerhalb de",
    "ausserhalb de",
    "ausland",
    "kein bezug",
    "no de",
)
STATUS_PRIORITY = {
    "Prüfen": 50,
    "Overlap": 40,
    "GAP": 30,
    "Zugewiesen": 20,
    "In DE": 10,
    "Außerhalb DE": 0,
}
STATUS_CSS_CLASS = {
    "Prüfen": "status-check",
    "Overlap": "status-overlap",
    "GAP": "status-gap",
    "Zugewiesen": "status-assigned",
    "In DE": "status-in-de",
    "Außerhalb DE": "status-outside",
}
SEGMENT_COLUMNS = [
    "Meldetag",
    "Loknummer",
    "Halter",
    "Nutzer / PerformingRU",
    "Status",
    "StatusPriorität",
    "Uhrzeit von",
    "Uhrzeit bis",
    "StartMinute",
    "EndMinute",
    "Route Type",
    "Event Type",
    "Row Type",
    "TransportNumber",
    "Regeln",
    "Meldung",
    "Begründung",
    "Tooltip",
    "Im Filterzeitraum",
]
SUMMARY_COLUMNS = [
    "Meldetag",
    "Loknummer",
    "Status",
    "StatusPriorität",
    "Halter",
    "Nutzer / PerformingRU",
    "Segmente",
    "Problemsegmente",
]
EMPTY_SEGMENTS = pd.DataFrame(columns=SEGMENT_COLUMNS)
EMPTY_SUMMARY = pd.DataFrame(columns=SUMMARY_COLUMNS)


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


def _text_value(row: pd.Series, column: str | None, fallback: str = "") -> str:
    if not column or column not in row.index:
        return fallback
    value = row.get(column, fallback)
    if pd.isna(value):
        return fallback
    return str(value).strip()


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


def _normalize_day_range(date_from: date, date_to: date) -> tuple[date, date]:
    return (date_from, date_to) if date_from <= date_to else (date_to, date_from)


def _contains_any(value: str, keywords: Iterable[str]) -> bool:
    normalized = str(value or "").strip().casefold()
    return any(keyword in normalized for keyword in keywords)


def _build_de_relevance_mask(source_df: pd.DataFrame) -> pd.Series:
    report_scope_col = _column(source_df, ["report_scope"])
    event_label_col = _column(source_df, EVENT_LABEL_COLUMNS)
    route_type_col = _column(source_df, ROUTE_TYPE_COLUMNS)

    masks: list[pd.Series] = []
    explicit_non_de = pd.Series(False, index=source_df.index, dtype=bool)
    if report_scope_col:
        masks.append(_text_series(source_df, report_scope_col).str.upper().eq("IN_REPORT"))
    if event_label_col:
        event_values = _text_series(source_df, event_label_col)
        masks.append(event_values.str.upper().isin(DE_EVENT_LABELS))
        explicit_non_de = explicit_non_de | event_values.apply(lambda value: _contains_any(value, NON_DE_KEYWORDS))
    if route_type_col:
        route_values = _text_series(source_df, route_type_col)
        route_positive = route_values.apply(lambda value: _contains_any(value, DE_ROUTE_KEYWORDS))
        route_non_de = route_values.apply(lambda value: _contains_any(value, NON_DE_KEYWORDS))
        masks.append(route_positive & ~route_non_de)
        explicit_non_de = explicit_non_de | route_non_de

    if not masks:
        return pd.Series(True, index=source_df.index, dtype=bool)

    result = masks[0]
    for mask in masks[1:]:
        result = result | mask
    return (result & ~explicit_non_de).fillna(False).astype(bool)


def _has_content(value: str) -> bool:
    cleaned = str(value or "").strip()
    return cleaned != "" and cleaned.casefold() not in {"nan", "none", "null"}


def _has_assignment(holder: str, performing_ru: str) -> bool:
    missing_values = {
        "",
        "nan",
        "none",
        "null",
        "(halter fehlt)",
        "(performingru fehlt)",
        "keine lte zuweisung",
    }
    return holder.strip().casefold() not in missing_values or performing_ru.strip().casefold() not in missing_values


def classify_timeline_status(
    *,
    row_type: str,
    is_de_relevant: bool,
    holder: str = "",
    performing_ru: str = "",
    rules: str = "",
    message: str = "",
    decision_reason: str = "",
) -> str:
    """Return the user-facing status with deterministic conflict priority."""
    row_type_upper = str(row_type or "").strip().upper()
    combined_text = " ".join([rules, message, decision_reason, row_type]).casefold()
    has_issue = _has_content(rules) or _has_content(message)
    has_overlap = (
        row_type_upper == "OVERLAP"
        or "overlap" in combined_text
        or "überschneid" in combined_text
        or "ueberschneid" in combined_text
        or "r011" in combined_text
    )
    has_gap = row_type_upper == "GAP" or "gap" in combined_text or "lücke" in combined_text

    if has_issue:
        return "Prüfen"
    if has_overlap:
        return "Overlap"
    if has_gap:
        return "GAP"
    if is_de_relevant and _has_assignment(holder, performing_ru):
        return "Zugewiesen"
    if is_de_relevant:
        return "In DE"
    return "Außerhalb DE"


def _format_time(value: pd.Timestamp) -> str:
    return pd.Timestamp(value).strftime("%H:%M")


def _join_unique(values: pd.Series) -> str:
    cleaned = sorted({str(value).strip() for value in values.dropna().tolist() if str(value).strip()})
    return " | ".join(cleaned)


def _iter_clipped_days(start_ts: pd.Timestamp, end_ts: pd.Timestamp):
    start_day = start_ts.floor("D")
    end_marker = end_ts - pd.Timedelta(microseconds=1)
    end_day = end_marker.floor("D")
    current_day = start_day
    while current_day <= end_day:
        day_start = current_day
        day_end = current_day + pd.Timedelta(days=1)
        clipped_start = max(start_ts, day_start)
        clipped_end = min(end_ts, day_end)
        if clipped_end > clipped_start:
            yield current_day.date(), clipped_start, clipped_end
        current_day += pd.Timedelta(days=1)


def build_loco_timeline_segments(
    source_df: pd.DataFrame,
    *,
    date_from: date,
    date_to: date,
    context_days: int = 1,
) -> pd.DataFrame:
    """Build day-clipped locomotive timeline bands for the selected period plus context days."""
    if source_df.empty:
        return EMPTY_SEGMENTS.copy()

    date_from, date_to = _normalize_day_range(date_from, date_to)
    context_days = max(int(context_days), 0)
    context_from = date_from - timedelta(days=context_days)
    context_to = date_to + timedelta(days=context_days)
    context_start = pd.Timestamp(context_from, tz="UTC")
    context_end = pd.Timestamp(context_to + timedelta(days=1), tz="UTC")
    filter_start = pd.Timestamp(date_from, tz="UTC")
    filter_end = pd.Timestamp(date_to + timedelta(days=1), tz="UTC")

    work = source_df.copy()
    start_ts = _coalesced_timestamp(work, START_TIME_COLUMNS)
    end_ts = _coalesced_timestamp(work, END_TIME_COLUMNS)
    fallback_end = start_ts + pd.Timedelta(minutes=15)
    end_ts = end_ts.fillna(fallback_end)
    invalid_end_mask = start_ts.notna() & (end_ts <= start_ts)
    end_ts.loc[invalid_end_mask] = start_ts.loc[invalid_end_mask] + pd.Timedelta(minutes=15)

    overlap_mask = start_ts.notna() & end_ts.gt(context_start) & start_ts.lt(context_end)
    work = work.loc[overlap_mask].copy()
    start_ts = start_ts.loc[work.index]
    end_ts = end_ts.loc[work.index]
    if work.empty:
        return EMPTY_SEGMENTS.copy()

    de_relevance = _build_de_relevance_mask(work)
    work = work.loc[de_relevance].copy()
    start_ts = start_ts.loc[work.index]
    end_ts = end_ts.loc[work.index]
    de_relevance = de_relevance.loc[work.index]
    if work.empty:
        return EMPTY_SEGMENTS.copy()

    loco_col = _column(work, LOCO_COLUMNS)
    holder_col = _column(work, HOLDER_COLUMNS)
    performing_col = _column(work, PERFORMING_RU_COLUMNS)
    route_col = _column(work, ROUTE_TYPE_COLUMNS)
    event_col = _column(work, EVENT_LABEL_COLUMNS)
    row_type_col = _column(work, ROW_TYPE_COLUMNS)
    message_col = _column(work, MESSAGE_COLUMNS)
    rule_col = _column(work, RULE_COLUMNS)
    decision_col = _column(work, DECISION_COLUMNS)
    transport_col = _column(work, TRANSPORT_COLUMNS)

    if not loco_col:
        return EMPTY_SEGMENTS.copy()

    rows: list[dict[str, object]] = []
    for row_index, row in work.iterrows():
        loco = _text_value(row, loco_col)
        if not loco or loco == "00000000000-0":
            continue
        row_start = max(pd.Timestamp(start_ts.loc[row_index]), context_start)
        row_end = min(pd.Timestamp(end_ts.loc[row_index]), context_end)
        if row_end <= row_start:
            continue
        holder = _text_value(row, holder_col, "(Halter fehlt)") or "(Halter fehlt)"
        performing_ru = _text_value(row, performing_col, "(PerformingRU fehlt)") or "(PerformingRU fehlt)"
        route_type = _text_value(row, route_col)
        event_type = _text_value(row, event_col)
        row_type = _text_value(row, row_type_col)
        message = _text_value(row, message_col)
        rules = _text_value(row, rule_col)
        decision = _text_value(row, decision_col)
        transport = _text_value(row, transport_col)
        is_de = bool(de_relevance.loc[row_index])
        status = classify_timeline_status(
            row_type=row_type,
            is_de_relevant=is_de,
            holder=holder,
            performing_ru=performing_ru,
            rules=rules,
            message=message,
            decision_reason=decision,
        )
        for day_value, clipped_start, clipped_end in _iter_clipped_days(row_start, row_end):
            start_minute = int((clipped_start - clipped_start.floor("D")).total_seconds() // 60)
            end_minute = int((clipped_end - clipped_end.floor("D")).total_seconds() // 60)
            if end_minute == 0 and clipped_end > clipped_start:
                end_minute = 24 * 60
            end_minute = max(end_minute, start_minute + 1)
            end_minute = min(end_minute, 24 * 60)
            tooltip_parts = [
                f"Lok {loco}",
                f"{_format_time(clipped_start)}-{_format_time(clipped_end)} UTC",
                f"Status: {status}",
                f"Halter: {holder}",
                f"Nutzer/PerformingRU: {performing_ru}",
            ]
            if transport:
                tooltip_parts.append(f"Transport: {transport}")
            if route_type:
                tooltip_parts.append(f"Route: {route_type}")
            if event_type:
                tooltip_parts.append(f"Event: {event_type}")
            if rules:
                tooltip_parts.append(f"Regeln: {rules}")
            if message:
                tooltip_parts.append(f"Meldung: {message}")
            if decision:
                tooltip_parts.append(f"Begründung: {decision}")
            rows.append(
                {
                    "Meldetag": day_value.isoformat(),
                    "Loknummer": loco,
                    "Halter": holder,
                    "Nutzer / PerformingRU": performing_ru,
                    "Status": status,
                    "StatusPriorität": STATUS_PRIORITY[status],
                    "Uhrzeit von": _format_time(clipped_start),
                    "Uhrzeit bis": _format_time(clipped_end),
                    "StartMinute": start_minute,
                    "EndMinute": end_minute,
                    "Route Type": route_type,
                    "Event Type": event_type,
                    "Row Type": row_type,
                    "TransportNumber": transport,
                    "Regeln": rules,
                    "Meldung": message,
                    "Begründung": decision,
                    "Tooltip": " | ".join(tooltip_parts),
                    "Im Filterzeitraum": bool(clipped_end > filter_start and clipped_start < filter_end),
                }
            )

    if not rows:
        return EMPTY_SEGMENTS.copy()
    result = pd.DataFrame(rows, columns=SEGMENT_COLUMNS)
    return result.sort_values(
        by=["Meldetag", "Loknummer", "StartMinute", "StatusPriorität"],
        ascending=[True, True, True, False],
        kind="stable",
    ).reset_index(drop=True)


def build_loco_timeline_day_summary(segments_df: pd.DataFrame) -> pd.DataFrame:
    if segments_df.empty:
        return EMPTY_SUMMARY.copy()
    grouped = (
        segments_df.groupby(["Meldetag", "Loknummer"], dropna=False)
        .agg(
            StatusPriorität=("StatusPriorität", "max"),
            Halter=("Halter", _join_unique),
            **{
                "Nutzer / PerformingRU": ("Nutzer / PerformingRU", _join_unique),
                "Segmente": ("Status", "size"),
                "Problemsegmente": ("Status", lambda values: int(values.isin(["Prüfen", "Overlap", "GAP"]).sum())),
            },
        )
        .reset_index()
    )
    priority_to_status = {priority: status for status, priority in STATUS_PRIORITY.items()}
    grouped["Status"] = grouped["StatusPriorität"].map(priority_to_status).fillna("Außerhalb DE")
    return grouped[SUMMARY_COLUMNS].sort_values(
        by=["Meldetag", "Loknummer"],
        ascending=True,
        kind="stable",
    ).reset_index(drop=True)


def filter_loco_timeline_segments(
    segments_df: pd.DataFrame,
    *,
    holder: str = "Alle",
    performing_ru: str = "Alle",
    status: str = "Alle",
    loco_query: str = "",
    only_problem_cases: bool = False,
) -> pd.DataFrame:
    if segments_df.empty:
        return segments_df.copy()
    filtered = segments_df.copy()
    if holder != "Alle":
        filtered = filtered[filtered["Halter"].astype(str).eq(holder)].copy()
    if performing_ru != "Alle":
        filtered = filtered[filtered["Nutzer / PerformingRU"].astype(str).eq(performing_ru)].copy()
    if status != "Alle":
        filtered = filtered[filtered["Status"].astype(str).eq(status)].copy()
    if only_problem_cases:
        filtered = filtered[filtered["Status"].isin(["Prüfen", "Overlap", "GAP"])].copy()
    query = loco_query.strip().casefold()
    if query:
        filtered = filtered[
            filtered["Loknummer"].astype(str).str.casefold().str.contains(query, na=False)
        ].copy()
    return filtered.reset_index(drop=True)


def build_loco_timeline_xlsx(segments_df: pd.DataFrame, summary_df: pd.DataFrame) -> bytes:
    """Build a reviewable XLSX export for the currently filtered locomotive timeline."""
    legend = pd.DataFrame(
        [
            {"Status": "Prüfen", "Priorität": STATUS_PRIORITY["Prüfen"], "Bedeutung": "Regelmeldung oder fachlicher Prüffall vorhanden"},
            {"Status": "Overlap", "Priorität": STATUS_PRIORITY["Overlap"], "Bedeutung": "Überschneidung erkannt"},
            {"Status": "GAP", "Priorität": STATUS_PRIORITY["GAP"], "Bedeutung": "Zeitliche Lücke erkannt"},
            {"Status": "Zugewiesen", "Priorität": STATUS_PRIORITY["Zugewiesen"], "Bedeutung": "DE-relevanter Zeitraum mit Halter/Nutzer-Zuordnung"},
            {"Status": "In DE", "Priorität": STATUS_PRIORITY["In DE"], "Bedeutung": "DE-relevanter Zeitraum ohne explizite Zuordnungsanzeige"},
            {"Status": "Außerhalb DE", "Priorität": STATUS_PRIORITY["Außerhalb DE"], "Bedeutung": "Kontext oder nicht DE-relevanter Zeitraum"},
        ]
    )
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="Tagesstatus", index=False)
        segments_df.to_excel(writer, sheet_name="Segmente", index=False)
        legend.to_excel(writer, sheet_name="Legende", index=False)

        for sheet_name in ["Tagesstatus", "Segmente", "Legende"]:
            worksheet = writer.book[sheet_name]
            worksheet.freeze_panes = "A2"
            worksheet.auto_filter.ref = worksheet.dimensions
            for column_cells in worksheet.columns:
                header = str(column_cells[0].value or "")
                max_length = max([len(str(cell.value or "")) for cell in column_cells[:150]] + [len(header)])
                worksheet.column_dimensions[column_cells[0].column_letter].width = min(max(max_length + 2, 10), 48)
    return output.getvalue()


def _options(source_df: pd.DataFrame, column: str) -> list[str]:
    if source_df.empty or column not in source_df.columns:
        return []
    return sorted({str(value).strip() for value in source_df[column].dropna().tolist() if str(value).strip()})


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
    return _normalize_day_range(date_from, date_to)


def _timeline_css() -> str:
    return """
    <style>
    .loco-timeline-wrap {font-family: system-ui, -apple-system, Segoe UI, sans-serif;}
    .loco-timeline-legend {display:flex; flex-wrap:wrap; gap:.45rem; margin:.5rem 0 1rem 0;}
    .loco-timeline-chip {border-radius:999px; padding:.18rem .55rem; font-size:.78rem; border:1px solid rgba(0,0,0,.12); background:#fff;}
    .loco-row {display:grid; grid-template-columns: 270px 1fr; gap:.75rem; align-items:center; border-bottom:1px solid rgba(49,51,63,.12); padding:.38rem 0;}
    .loco-meta {font-size:.78rem; line-height:1.25; white-space:normal; overflow:hidden;}
    .loco-day {font-weight:700;}
    .loco-number {font-weight:700; font-size:.92rem;}
    .loco-track {position:relative; height:30px; border-radius:8px; background:linear-gradient(90deg, rgba(49,51,63,.05), rgba(49,51,63,.03)); overflow:hidden; border:1px solid rgba(49,51,63,.12);}
    .loco-hours {position:absolute; inset:0; background:linear-gradient(90deg, transparent 24.8%, rgba(0,0,0,.12) 25%, transparent 25.2%, transparent 49.8%, rgba(0,0,0,.12) 50%, transparent 50.2%, transparent 74.8%, rgba(0,0,0,.12) 75%, transparent 75.2%); pointer-events:none;}
    .loco-segment {position:absolute; top:4px; height:20px; border-radius:6px; border:1px solid rgba(0,0,0,.20); min-width:3px;}
    .status-check {background:#d62728;}
    .status-overlap {background:#ffbf00;}
    .status-gap {background:#ff7f0e;}
    .status-assigned {background:#2ca02c;}
    .status-in-de {background:#1f77b4;}
    .status-outside {background:#9aa0a6;}
    .context-muted {opacity:.46;}
    .hour-labels {display:grid; grid-template-columns: repeat(5, 1fr); font-size:.68rem; color:rgba(49,51,63,.72); margin-left:270px; padding-left:.75rem;}
    </style>
    """


def timeline_segments_to_html(segments_df: pd.DataFrame, *, max_rows: int = 140) -> str:
    if segments_df.empty:
        return "<p>Keine Zeitachsen-Segmente für die aktuelle Auswahl.</p>"
    rows_html: list[str] = [_timeline_css(), '<div class="loco-timeline-wrap">']
    rows_html.append(
        '<div class="loco-timeline-legend">'
        '<span class="loco-timeline-chip"><b style="color:#d62728">■</b> Prüfen</span>'
        '<span class="loco-timeline-chip"><b style="color:#ffbf00">■</b> Overlap</span>'
        '<span class="loco-timeline-chip"><b style="color:#ff7f0e">■</b> GAP</span>'
        '<span class="loco-timeline-chip"><b style="color:#2ca02c">■</b> Zugewiesen</span>'
        '<span class="loco-timeline-chip"><b style="color:#1f77b4">■</b> In DE</span>'
        '<span class="loco-timeline-chip"><b style="color:#9aa0a6">■</b> Außerhalb DE / Kontext</span>'
        '</div>'
    )
    rows_html.append('<div class="hour-labels"><span>00:00</span><span>06:00</span><span>12:00</span><span>18:00</span><span style="text-align:right">24:00</span></div>')

    grouped = list(segments_df.groupby(["Meldetag", "Loknummer"], sort=True, dropna=False))
    for (day_value, loco), group in grouped[:max_rows]:
        highest = group.sort_values("StatusPriorität", ascending=False).iloc[0]
        statuses = " | ".join(sorted(set(group["Status"].astype(str))))
        holders = " | ".join(sorted(set(group["Halter"].astype(str))))
        performers = " | ".join(sorted(set(group["Nutzer / PerformingRU"].astype(str))))
        meta = (
            f'<div class="loco-meta">'
            f'<div class="loco-day">{escape(str(day_value))}</div>'
            f'<div class="loco-number">{escape(str(loco))}</div>'
            f'<div>{escape(str(highest["Status"]))} · {escape(statuses)}</div>'
            f'<div>Halter: {escape(holders)}</div>'
            f'<div>Nutzer: {escape(performers)}</div>'
            f'</div>'
        )
        segments_html: list[str] = ['<div class="loco-track"><div class="loco-hours"></div>']
        for _, row in group.iterrows():
            left = max(0.0, min(100.0, float(row["StartMinute"]) / 1440.0 * 100.0))
            width = max(0.15, min(100.0 - left, (float(row["EndMinute"]) - float(row["StartMinute"])) / 1440.0 * 100.0))
            css_class = STATUS_CSS_CLASS.get(str(row["Status"]), "status-outside")
            context_class = "" if bool(row.get("Im Filterzeitraum", True)) else " context-muted"
            title = escape(str(row.get("Tooltip", "")), quote=True)
            segments_html.append(
                f'<div class="loco-segment {css_class}{context_class}" '
                f'style="left:{left:.4f}%; width:{width:.4f}%;" title="{title}"></div>'
            )
        segments_html.append("</div>")
        rows_html.append(f'<div class="loco-row">{meta}{"".join(segments_html)}</div>')

    if len(grouped) > max_rows:
        rows_html.append(
            f'<p style="font-size:.8rem; opacity:.75;">Weitere {len(grouped) - max_rows} Lok-Tage ausgeblendet. Bitte stärker filtern.</p>'
        )
    rows_html.append("</div>")
    return "".join(rows_html)


def render_loco_timeline_calendar() -> None:
    import streamlit as st
    import streamlit.components.v1 as components

    st.header("📅 Lok-Zeitachse")
    st.caption(
        "Kalenderartige Prüfoberfläche je Lok und Tag: zugewiesen, GAP, Overlap, "
        "Prüffall, DE-Bezug und Kontext außerhalb des gewählten Zeitraums."
    )

    date_from, date_to = _get_selected_day_range()
    st.info(
        f"Aktiver Arbeitszeitraum: {date_from:%d.%m.%Y} bis {date_to:%d.%m.%Y}. "
        "Für den Kontext wird automatisch jeweils ein Tag davor und danach mitgeladen."
    )

    source_df = _read_csv_safe(TIMELINE_PATH)
    if source_df.empty:
        st.warning("Keine core_loco_timeline.csv gefunden. Bitte zuerst die Tagesprüfung ausführen.")
        return

    segments = build_loco_timeline_segments(source_df, date_from=date_from, date_to=date_to, context_days=1)
    if segments.empty:
        st.info("Im gewählten Zeitraum und Kontext wurden keine Lok-Zeitachsen gefunden.")
        return

    summary = build_loco_timeline_day_summary(segments)
    metric_1, metric_2, metric_3, metric_4 = st.columns(4)
    with metric_1:
        st.metric("Loks", int(segments["Loknummer"].nunique()))
    with metric_2:
        st.metric("Lok-Tage", int(len(summary)))
    with metric_3:
        st.metric("Prüffälle", int((segments["Status"] == "Prüfen").sum()))
    with metric_4:
        st.metric("GAP/Overlap", int(segments["Status"].isin(["GAP", "Overlap"]).sum()))

    st.markdown("#### Filter")
    filter_1, filter_2, filter_3, filter_4, filter_5 = st.columns([1.2, 1.2, 1.0, 1.0, 1.0])
    with filter_1:
        selected_holder = st.selectbox("Halter", ["Alle"] + _options(segments, "Halter"), key="loco_timeline_holder")
    with filter_2:
        selected_performing_ru = st.selectbox(
            "Nutzer / PerformingRU",
            ["Alle"] + _options(segments, "Nutzer / PerformingRU"),
            key="loco_timeline_performing_ru",
        )
    with filter_3:
        selected_status = st.selectbox("Status", ["Alle"] + _options(segments, "Status"), key="loco_timeline_status")
    with filter_4:
        loco_query = st.text_input("Loknummer enthält", key="loco_timeline_loco_query")
    with filter_5:
        only_problem_cases = st.checkbox("Nur Probleme", value=False, key="loco_timeline_only_problems")

    filtered = filter_loco_timeline_segments(
        segments,
        holder=selected_holder,
        performing_ru=selected_performing_ru,
        status=selected_status,
        loco_query=loco_query,
        only_problem_cases=only_problem_cases,
    )
    filtered_summary = build_loco_timeline_day_summary(filtered)

    st.write(
        f"Angezeigte Segmente: **{len(filtered)}** · "
        f"Lok-Tage: **{len(filtered_summary)}**"
    )
    html = timeline_segments_to_html(filtered, max_rows=140)
    height = min(920, max(260, 145 + int(len(filtered_summary)) * 52))
    components.html(html, height=height, scrolling=True)

    with st.expander("Segmentdetails", expanded=False):
        visible_columns = [
            "Meldetag",
            "Loknummer",
            "Halter",
            "Nutzer / PerformingRU",
            "Status",
            "Uhrzeit von",
            "Uhrzeit bis",
            "Route Type",
            "Event Type",
            "Row Type",
            "TransportNumber",
            "Regeln",
            "Meldung",
            "Begründung",
            "Im Filterzeitraum",
        ]
        st.dataframe(filtered[visible_columns], use_container_width=True, hide_index=True, height=520)

    download_1, download_2 = st.columns(2)
    with download_1:
        csv = filtered.to_csv(index=False, sep=";").encode("utf-8-sig")
        st.download_button(
            "Lok-Zeitachse als CSV herunterladen",
            data=csv,
            file_name=f"lok_zeitachse_{date_from.isoformat()}_bis_{date_to.isoformat()}_plus_kontext.csv",
            mime="text/csv",
            key="download_loco_timeline_calendar_csv",
            use_container_width=True,
        )
    with download_2:
        xlsx = build_loco_timeline_xlsx(filtered, filtered_summary)
        st.download_button(
            "Lok-Zeitachse als XLSX herunterladen",
            data=xlsx,
            file_name=f"lok_zeitachse_{date_from.isoformat()}_bis_{date_to.isoformat()}_plus_kontext.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="download_loco_timeline_calendar_xlsx",
            use_container_width=True,
        )


def _visible_tab_labels(labels: Sequence[object]) -> tuple[list[object], int | None]:
    values = [str(label) for label in labels]
    if TIMELINE_TAB_LABEL in values or TIMELINE_TAB_LABEL_WITHOUT_WATERFALL in values:
        return list(labels), None
    if LOCO_TAB_LABEL not in values:
        return list(labels), None

    visible_labels = list(labels)
    if WATERFALL_TAB_LABEL in values:
        timeline_index = values.index(WATERFALL_TAB_LABEL) + 1
        visible_labels.insert(timeline_index, TIMELINE_TAB_LABEL)
        for export_label in EXPORT_TAB_LABELS:
            current_values = [str(label) for label in visible_labels]
            if export_label in current_values:
                visible_labels[current_values.index(export_label)] = EXPORT_TAB_RENUMBERED_LABEL
                break
        return visible_labels, timeline_index

    export_label = next((label for label in EXPORT_TAB_LABELS if label in values), None)
    if export_label is None:
        return list(labels), None
    export_index = values.index(export_label)
    visible_labels[export_index] = "6. Exporte erstellen"
    timeline_index = values.index(LOCO_TAB_LABEL) + 1
    visible_labels.insert(timeline_index, TIMELINE_TAB_LABEL_WITHOUT_WATERFALL)
    return visible_labels, timeline_index


def install_loco_timeline_calendar_runtime():
    """Add the locomotive day timeline tab without changing the legacy app tab contract."""
    import streamlit as st

    original_tabs = st.tabs
    if getattr(original_tabs, "_loco_timeline_calendar_installed", False):
        return original_tabs

    def patched_tabs(labels: Sequence[object], *args, **kwargs):
        visible_labels, timeline_index = _visible_tab_labels(labels)
        if timeline_index is None:
            return original_tabs(labels, *args, **kwargs)
        rendered_tabs = list(original_tabs(visible_labels, *args, **kwargs))
        if 0 <= timeline_index < len(rendered_tabs):
            with rendered_tabs[timeline_index]:
                render_loco_timeline_calendar()
            return rendered_tabs[:timeline_index] + rendered_tabs[timeline_index + 1:]
        return rendered_tabs

    patched_tabs._loco_timeline_calendar_installed = True
    st.tabs = patched_tabs
    return original_tabs


def restore_loco_timeline_calendar_runtime(original_tabs) -> None:
    if original_tabs is None:
        return
    import streamlit as st

    st.tabs = original_tabs
