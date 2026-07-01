from __future__ import annotations

from io import BytesIO
from typing import Callable

import pandas as pd

import loco_timeline_calendar_runtime_module as timeline
from broken_route_chain_policy_module import is_no_lte_assignment_marker

NO_LTE_ASSIGNMENT_UI_MARKER = "NETZENTGELT_NO_LTE_ASSIGNMENT_GREY_TIMELINE_V2_20260701"

OUTSIDE_REPORT_MARKERS = (
    "not_in_report",
    "not in report",
    "not in the report",
    "outside_report",
    "outside report",
    "out_of_scope",
    "out of scope",
    "außerhalb bericht",
    "ausserhalb bericht",
)

TIMELINE_DEBUG_COLUMNS = [
    "Quelle",
    "Source Row ID",
    "Berechneter fachlicher Status",
    "Report-Scope",
    "UI-Status",
    "UI-Farbe",
    "Statusentscheidung",
    "row_type",
    "report_scope",
    "de_event_label",
    "cal_route_type_home",
    "gap_relevant_de",
    "is_de_relevant",
    "needs_manual_review",
    "dq_severity",
    "dq_message",
    "holder_name",
    "performing_ru",
    "decision_reason",
]

STATUS_COLOR_LABELS = {
    "Prüfen": "rot / status-check",
    "Overlap": "gelb / status-overlap",
    "GAP": "orange / status-gap",
    "Zugewiesen": "grün / status-assigned",
    "In DE": "blau / status-in-de",
    "Außerhalb DE": "grau / status-outside",
}


def _normalize_marker_text(value: object) -> str:
    return str(value or "").strip().casefold().replace("_", " ")


def is_outside_report_marker(*values: object) -> bool:
    """Return True for explicit NOT_IN_REPORT / outside report markers."""
    combined_raw = " ".join(str(value or "") for value in values).strip().casefold()
    combined_normalized = _normalize_marker_text(combined_raw)
    return any(marker.replace("_", " ") in combined_normalized for marker in OUTSIDE_REPORT_MARKERS)


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


def _boolish(value: object) -> bool:
    return str(value or "").strip().casefold() in {"1", "true", "yes", "ja", "y"}


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
        "keine lte zuordnung",
        "kein lte bezug",
        "no lte assignment",
    }
    return holder.strip().casefold() not in missing_values or performing_ru.strip().casefold() not in missing_values


def _row_has_no_lte_marker(row: pd.Series, columns: list[str | None]) -> bool:
    return is_no_lte_assignment_marker(*(_text_value(row, column) for column in columns if column))


def _source_de_relevance_mask(source_df: pd.DataFrame) -> pd.Series:
    """Central DE relevance for the timeline: NOT_IN_REPORT and explicit no-LTE are hard outside."""
    if source_df.empty:
        return pd.Series(False, index=source_df.index, dtype=bool)

    report_scope_col = timeline._column(source_df, ["report_scope"])
    event_label_col = timeline._column(source_df, timeline.EVENT_LABEL_COLUMNS)
    route_type_col = timeline._column(source_df, timeline.ROUTE_TYPE_COLUMNS)
    holder_col = timeline._column(source_df, timeline.HOLDER_COLUMNS)
    performing_col = timeline._column(source_df, timeline.PERFORMING_RU_COLUMNS)
    rule_col = timeline._column(source_df, timeline.RULE_COLUMNS)
    message_col = timeline._column(source_df, ["dq_message", *timeline.MESSAGE_COLUMNS])
    decision_col = timeline._column(source_df, timeline.DECISION_COLUMNS)

    masks: list[pd.Series] = []
    hard_outside = pd.Series(False, index=source_df.index, dtype=bool)

    if report_scope_col:
        report_values = _text_series(source_df, report_scope_col)
        masks.append(report_values.str.upper().eq("IN_REPORT"))
        hard_outside = hard_outside | report_values.apply(is_outside_report_marker)

    if event_label_col:
        event_values = _text_series(source_df, event_label_col)
        masks.append(event_values.str.upper().isin(timeline.DE_EVENT_LABELS))
        hard_outside = hard_outside | event_values.apply(
            lambda value: timeline._contains_any(value, timeline.NON_DE_KEYWORDS) or is_outside_report_marker(value)
        )

    if route_type_col:
        route_values = _text_series(source_df, route_type_col)
        route_positive = route_values.apply(lambda value: timeline._contains_any(value, timeline.DE_ROUTE_KEYWORDS))
        route_non_de = route_values.apply(lambda value: timeline._contains_any(value, timeline.NON_DE_KEYWORDS))
        masks.append(route_positive & ~route_non_de)
        hard_outside = hard_outside | route_non_de | route_values.apply(is_outside_report_marker)

    marker_columns = [holder_col, performing_col, rule_col, message_col, decision_col, event_label_col, route_type_col]
    hard_outside = hard_outside | source_df.apply(lambda row: _row_has_no_lte_marker(row, marker_columns), axis=1)

    if not masks:
        positive = pd.Series(True, index=source_df.index, dtype=bool)
    else:
        positive = masks[0]
        for mask in masks[1:]:
            positive = positive | mask

    return (positive & ~hard_outside).fillna(False).astype(bool)


def _has_overlap(row_type_upper: str, combined_text: str) -> bool:
    return (
        row_type_upper == "OVERLAP"
        or "overlap" in combined_text
        or "überschneid" in combined_text
        or "ueberschneid" in combined_text
        or "r011" in combined_text
    )


def _has_gap(row_type_upper: str, combined_text: str, gap_relevant_de: object = "") -> bool:
    return (
        row_type_upper == "GAP"
        or _boolish(gap_relevant_de)
        or "gap" in combined_text
        or "lücke" in combined_text
    )


def decide_timeline_status(
    *,
    row_type: str,
    is_de_relevant: bool,
    holder: str = "",
    performing_ru: str = "",
    rules: str = "",
    message: str = "",
    decision_reason: str = "",
    report_scope: str = "",
    route_type: str = "",
    event_type: str = "",
    gap_relevant_de: object = "",
    needs_manual_review: object = "",
    dq_severity: str = "",
) -> tuple[str, str]:
    """Return UI status and explanation from one central status decision."""
    row_type_upper = str(row_type or "").strip().upper()
    severity_upper = str(dq_severity or "").strip().upper()
    combined_text = " ".join(
        [rules, message, decision_reason, row_type, report_scope, route_type, event_type, severity_upper]
    ).casefold()

    if is_outside_report_marker(row_type, report_scope, message, decision_reason, event_type, route_type):
        return "Außerhalb DE", "Report-Scope/Marker ist NOT_IN_REPORT bzw. außerhalb Bericht; daher niemals grün."

    if is_no_lte_assignment_marker(row_type, holder, performing_ru, rules, message, decision_reason, event_type, route_type):
        return "Außerhalb DE", "Explizite Keine-LTE-Zuordnung/Zuweisung; bewusst grau als außerhalb DE."

    if not is_de_relevant:
        return "Außerhalb DE", "Keine DE-Relevanz nach zentraler Relevanzentscheidung."

    if _has_overlap(row_type_upper, combined_text):
        return "Overlap", "Überschneidung/Konflikt erkannt."

    if _has_gap(row_type_upper, combined_text, gap_relevant_de):
        return "GAP", "Normale DE-relevante Lücke; bleibt GAP und prüfrelevant."

    has_manual_review = _boolish(needs_manual_review)
    has_severity_issue = severity_upper in {"ERROR", "FEHLER", "CRITICAL", "BLOCKER", "MANUAL_REVIEW", "REVIEW", "WARNING"}
    has_issue = _has_content(rules) or _has_content(message) or has_manual_review or has_severity_issue
    if has_issue:
        return "Prüfen", "Regelmeldung, Severity oder manuelle Prüfung vorhanden."

    if _has_assignment(holder, performing_ru):
        return "Zugewiesen", "DE-relevant, im Report und Halter/Nutzer-Zuordnung vorhanden."

    return "In DE", "DE-relevant und im Report, aber ohne vollständige explizite Zuordnung."


def _build_debug_timeline_segments(
    source_df: pd.DataFrame,
    *,
    date_from,
    date_to,
    context_days: int = 1,
) -> pd.DataFrame:
    """Build timeline segments with source/debug fields and one central UI status decision."""
    if source_df.empty:
        return timeline.EMPTY_SEGMENTS.copy()

    date_from, date_to = timeline._normalize_day_range(date_from, date_to)
    context_days = max(int(context_days), 0)
    context_from = date_from - pd.Timedelta(days=context_days).to_pytimedelta()
    context_to = date_to + pd.Timedelta(days=context_days).to_pytimedelta()
    context_start = pd.Timestamp(context_from, tz="UTC")
    context_end = pd.Timestamp(context_to + pd.Timedelta(days=1).to_pytimedelta(), tz="UTC")
    filter_start = pd.Timestamp(date_from, tz="UTC")
    filter_end = pd.Timestamp(date_to + pd.Timedelta(days=1).to_pytimedelta(), tz="UTC")

    work = source_df.copy()
    start_ts = timeline._coalesced_timestamp(work, timeline.START_TIME_COLUMNS)
    end_ts = timeline._coalesced_timestamp(work, timeline.END_TIME_COLUMNS)
    fallback_end = start_ts + pd.Timedelta(minutes=15)
    end_ts = end_ts.fillna(fallback_end)
    invalid_end_mask = start_ts.notna() & (end_ts <= start_ts)
    end_ts.loc[invalid_end_mask] = start_ts.loc[invalid_end_mask] + pd.Timedelta(minutes=15)

    overlap_mask = start_ts.notna() & end_ts.gt(context_start) & start_ts.lt(context_end)
    work = work.loc[overlap_mask].copy()
    start_ts = start_ts.loc[work.index]
    end_ts = end_ts.loc[work.index]
    if work.empty:
        return timeline.EMPTY_SEGMENTS.copy()

    loco_col = timeline._column(work, timeline.LOCO_COLUMNS)
    if not loco_col:
        return timeline.EMPTY_SEGMENTS.copy()

    de_relevance = _source_de_relevance_mask(work)
    overlaps_active_period = start_ts.notna() & end_ts.gt(filter_start) & start_ts.lt(filter_end)
    loco_values = work[loco_col].fillna("").astype(str).str.strip()
    relevant_loco_values = set(
        loco_values.loc[
            de_relevance
            & overlaps_active_period
            & loco_values.ne("")
            & loco_values.ne("00000000000-0")
        ].tolist()
    )
    if not relevant_loco_values:
        return timeline.EMPTY_SEGMENTS.copy()

    relevant_loco_mask = loco_values.isin(relevant_loco_values)
    work = work.loc[relevant_loco_mask].copy()
    start_ts = start_ts.loc[work.index]
    end_ts = end_ts.loc[work.index]
    de_relevance = de_relevance.loc[work.index]
    if work.empty:
        return timeline.EMPTY_SEGMENTS.copy()

    holder_col = timeline._column(work, timeline.HOLDER_COLUMNS)
    performing_col = timeline._column(work, timeline.PERFORMING_RU_COLUMNS)
    route_col = timeline._column(work, timeline.ROUTE_TYPE_COLUMNS)
    event_col = timeline._column(work, timeline.EVENT_LABEL_COLUMNS)
    row_type_col = timeline._column(work, timeline.ROW_TYPE_COLUMNS)
    message_col = timeline._column(work, ["dq_message", *timeline.MESSAGE_COLUMNS])
    rule_col = timeline._column(work, timeline.RULE_COLUMNS)
    decision_col = timeline._column(work, timeline.DECISION_COLUMNS)
    transport_col = timeline._column(work, timeline.TRANSPORT_COLUMNS)
    report_scope_col = timeline._column(work, ["report_scope"])
    gap_relevant_col = timeline._column(work, ["gap_relevant_de"])
    manual_col = timeline._column(work, ["needs_manual_review"])
    severity_col = timeline._column(work, ["dq_severity"])
    source_table_col = timeline._column(work, ["source_table"])
    source_row_id_col = timeline._column(work, ["source_row_id", "source_row_hash", "row_hash"])

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
        report_scope = _text_value(row, report_scope_col)
        gap_relevant_de = _text_value(row, gap_relevant_col)
        needs_manual_review = _text_value(row, manual_col)
        dq_severity = _text_value(row, severity_col)
        source_table = _text_value(row, source_table_col)
        source_row_id = _text_value(row, source_row_id_col)
        is_de = bool(de_relevance.loc[row_index])

        status, status_reason = decide_timeline_status(
            row_type=row_type,
            is_de_relevant=is_de,
            holder=holder,
            performing_ru=performing_ru,
            rules=rules,
            message=message,
            decision_reason=decision,
            report_scope=report_scope,
            route_type=route_type,
            event_type=event_type,
            gap_relevant_de=gap_relevant_de,
            needs_manual_review=needs_manual_review,
            dq_severity=dq_severity,
        )

        for day_value, clipped_start, clipped_end in timeline._iter_clipped_days(row_start, row_end):
            start_minute = int((clipped_start - clipped_start.floor("D")).total_seconds() // 60)
            end_minute = int((clipped_end - clipped_end.floor("D")).total_seconds() // 60)
            if end_minute == 0 and clipped_end > clipped_start:
                end_minute = 24 * 60
            end_minute = max(end_minute, start_minute + 1)
            end_minute = min(end_minute, 24 * 60)

            tooltip_parts = [
                f"Lok {loco}",
                f"{timeline._format_time(clipped_start)}-{timeline._format_time(clipped_end)} UTC",
                f"Status: {status}",
                f"Report-Scope: {report_scope or '(leer)'}",
                f"Statusentscheidung: {status_reason}",
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

            row_dict = {
                "Meldetag": day_value.isoformat(),
                "Loknummer": loco,
                "Halter": holder,
                "Nutzer / PerformingRU": performing_ru,
                "Status": status,
                "StatusPriorität": timeline.STATUS_PRIORITY[status],
                "Uhrzeit von": timeline._format_time(clipped_start),
                "Uhrzeit bis": timeline._format_time(clipped_end),
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
                "Quelle": source_table,
                "Source Row ID": source_row_id,
                "Berechneter fachlicher Status": status,
                "Report-Scope": report_scope,
                "UI-Status": status,
                "UI-Farbe": STATUS_COLOR_LABELS.get(status, ""),
                "Statusentscheidung": status_reason,
                "row_type": row_type,
                "report_scope": report_scope,
                "de_event_label": event_type,
                "cal_route_type_home": route_type,
                "gap_relevant_de": gap_relevant_de,
                "is_de_relevant": is_de,
                "needs_manual_review": needs_manual_review,
                "dq_severity": dq_severity,
                "dq_message": message,
                "holder_name": holder,
                "performing_ru": performing_ru,
                "decision_reason": decision,
            }
            rows.append(row_dict)

    if not rows:
        return timeline.EMPTY_SEGMENTS.copy()

    result = pd.DataFrame(rows)
    ordered_columns = list(timeline.SEGMENT_COLUMNS) + [column for column in TIMELINE_DEBUG_COLUMNS if column in result.columns]
    return result[ordered_columns].sort_values(
        by=["Meldetag", "Loknummer", "StartMinute", "StatusPriorität"],
        ascending=[True, True, True, False],
        kind="stable",
    ).reset_index(drop=True)


def _timeline_debug_frame(segments_df: pd.DataFrame) -> pd.DataFrame:
    if segments_df.empty:
        return pd.DataFrame(columns=TIMELINE_DEBUG_COLUMNS)
    columns = [column for column in TIMELINE_DEBUG_COLUMNS if column in segments_df.columns]
    return segments_df[columns].copy()


def _build_timeline_xlsx_with_debug(segments_df: pd.DataFrame, summary_df: pd.DataFrame) -> bytes:
    legend = pd.DataFrame(
        [
            {"Status": "Prüfen", "Priorität": timeline.STATUS_PRIORITY["Prüfen"], "Farbe": STATUS_COLOR_LABELS["Prüfen"], "Bedeutung": "Regelmeldung, Konflikt oder manuelle Prüfung vorhanden"},
            {"Status": "Overlap", "Priorität": timeline.STATUS_PRIORITY["Overlap"], "Farbe": STATUS_COLOR_LABELS["Overlap"], "Bedeutung": "Überschneidung erkannt"},
            {"Status": "GAP", "Priorität": timeline.STATUS_PRIORITY["GAP"], "Farbe": STATUS_COLOR_LABELS["GAP"], "Bedeutung": "Normale zeitliche Lücke; bleibt prüfrelevant"},
            {"Status": "Zugewiesen", "Priorität": timeline.STATUS_PRIORITY["Zugewiesen"], "Farbe": STATUS_COLOR_LABELS["Zugewiesen"], "Bedeutung": "DE-relevant, im Report und Halter/Nutzer-Zuordnung vorhanden"},
            {"Status": "In DE", "Priorität": timeline.STATUS_PRIORITY["In DE"], "Farbe": STATUS_COLOR_LABELS["In DE"], "Bedeutung": "DE-relevant, im Report, aber ohne vollständige Zuordnungsanzeige"},
            {"Status": "Außerhalb DE", "Priorität": timeline.STATUS_PRIORITY["Außerhalb DE"], "Farbe": STATUS_COLOR_LABELS["Außerhalb DE"], "Bedeutung": "Nicht DE-relevant, NOT_IN_REPORT oder explizite Keine-LTE-Zuordnung"},
        ]
    )
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="Tagesstatus", index=False)
        segments_df.to_excel(writer, sheet_name="Segmente", index=False)
        _timeline_debug_frame(segments_df).to_excel(writer, sheet_name="Timeline_Debug", index=False)
        legend.to_excel(writer, sheet_name="Legende", index=False)

        for sheet_name in ["Tagesstatus", "Segmente", "Timeline_Debug", "Legende"]:
            worksheet = writer.book[sheet_name]
            worksheet.freeze_panes = "A2"
            worksheet.auto_filter.ref = worksheet.dimensions
            for column_cells in worksheet.columns:
                header = str(column_cells[0].value or "")
                max_length = max([len(str(cell.value or "")) for cell in column_cells[:150]] + [len(header)])
                worksheet.column_dimensions[column_cells[0].column_letter].width = min(max(max_length + 2, 10), 56)
    return output.getvalue()


def install_no_lte_assignment_policy_runtime() -> dict[str, Callable | None] | Callable | None:
    """Install central timeline status policy: NOT_IN_REPORT/no-LTE never render green."""
    original_classifier = timeline.classify_timeline_status
    if getattr(original_classifier, "_no_lte_assignment_policy_installed", False):
        return getattr(original_classifier, "_no_lte_assignment_policy_originals", original_classifier)

    originals: dict[str, Callable | None] = {
        "classifier": original_classifier,
        "de_relevance": timeline._build_de_relevance_mask,
        "segments": timeline.build_loco_timeline_segments,
        "xlsx": timeline.build_loco_timeline_xlsx,
    }

    def classify_without_no_lte_as_problem(
        *,
        row_type: str,
        is_de_relevant: bool,
        holder: str = "",
        performing_ru: str = "",
        rules: str = "",
        message: str = "",
        decision_reason: str = "",
    ) -> str:
        status, _ = decide_timeline_status(
            row_type=row_type,
            is_de_relevant=is_de_relevant,
            holder=holder,
            performing_ru=performing_ru,
            rules=rules,
            message=message,
            decision_reason=decision_reason,
        )
        return status

    classify_without_no_lte_as_problem._no_lte_assignment_policy_installed = True
    classify_without_no_lte_as_problem._no_lte_assignment_policy_original = original_classifier
    classify_without_no_lte_as_problem._no_lte_assignment_policy_originals = originals
    timeline.classify_timeline_status = classify_without_no_lte_as_problem
    timeline._build_de_relevance_mask = _source_de_relevance_mask
    timeline.build_loco_timeline_segments = _build_debug_timeline_segments
    timeline.build_loco_timeline_xlsx = _build_timeline_xlsx_with_debug
    return originals


def restore_no_lte_assignment_policy_runtime(original_classifier: dict[str, Callable | None] | Callable | None) -> None:
    if original_classifier is None:
        return
    if isinstance(original_classifier, dict):
        if original_classifier.get("classifier") is not None:
            timeline.classify_timeline_status = original_classifier["classifier"]
        if original_classifier.get("de_relevance") is not None:
            timeline._build_de_relevance_mask = original_classifier["de_relevance"]
        if original_classifier.get("segments") is not None:
            timeline.build_loco_timeline_segments = original_classifier["segments"]
        if original_classifier.get("xlsx") is not None:
            timeline.build_loco_timeline_xlsx = original_classifier["xlsx"]
        return
    timeline.classify_timeline_status = original_classifier
