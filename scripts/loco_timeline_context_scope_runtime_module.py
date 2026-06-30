from __future__ import annotations

from datetime import date, timedelta
from typing import Callable

import pandas as pd

import loco_timeline_calendar_runtime_module as timeline


def _build_context_scoped_segments(
    source_df: pd.DataFrame,
    *,
    date_from: date,
    date_to: date,
    context_days: int = 1,
) -> pd.DataFrame:
    """Build timeline segments for DE-relevant locos, including visible outside-DE context."""
    if source_df.empty:
        return timeline.EMPTY_SEGMENTS.copy()

    date_from, date_to = timeline._normalize_day_range(date_from, date_to)
    context_days = max(int(context_days), 0)
    context_from = date_from - timedelta(days=context_days)
    context_to = date_to + timedelta(days=context_days)
    context_start = pd.Timestamp(context_from, tz="UTC")
    context_end = pd.Timestamp(context_to + timedelta(days=1), tz="UTC")
    filter_start = pd.Timestamp(date_from, tz="UTC")
    filter_end = pd.Timestamp(date_to + timedelta(days=1), tz="UTC")

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

    de_relevance = timeline._build_de_relevance_mask(work)
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
    message_col = timeline._column(work, timeline.MESSAGE_COLUMNS)
    rule_col = timeline._column(work, timeline.RULE_COLUMNS)
    decision_col = timeline._column(work, timeline.DECISION_COLUMNS)
    transport_col = timeline._column(work, timeline.TRANSPORT_COLUMNS)

    rows: list[dict[str, object]] = []
    for row_index, row in work.iterrows():
        loco = timeline._text_value(row, loco_col)
        if not loco or loco == "00000000000-0":
            continue
        row_start = max(pd.Timestamp(start_ts.loc[row_index]), context_start)
        row_end = min(pd.Timestamp(end_ts.loc[row_index]), context_end)
        if row_end <= row_start:
            continue

        holder = timeline._text_value(row, holder_col, "(Halter fehlt)") or "(Halter fehlt)"
        performing_ru = timeline._text_value(row, performing_col, "(PerformingRU fehlt)") or "(PerformingRU fehlt)"
        route_type = timeline._text_value(row, route_col)
        event_type = timeline._text_value(row, event_col)
        row_type = timeline._text_value(row, row_type_col)
        message = timeline._text_value(row, message_col)
        rules = timeline._text_value(row, rule_col)
        decision = timeline._text_value(row, decision_col)
        transport = timeline._text_value(row, transport_col)
        is_de = bool(de_relevance.loc[row_index])

        if not is_de:
            status = "Außerhalb DE"
        else:
            status = timeline.classify_timeline_status(
                row_type=row_type,
                is_de_relevant=is_de,
                holder=holder,
                performing_ru=performing_ru,
                rules=rules,
                message=message,
                decision_reason=decision,
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
                }
            )

    if not rows:
        return timeline.EMPTY_SEGMENTS.copy()
    result = pd.DataFrame(rows, columns=timeline.SEGMENT_COLUMNS)
    return result.sort_values(
        by=["Meldetag", "Loknummer", "StartMinute", "StatusPriorität"],
        ascending=[True, True, True, False],
        kind="stable",
    ).reset_index(drop=True)


def install_loco_timeline_context_scope_runtime() -> Callable | None:
    original_builder = timeline.build_loco_timeline_segments
    if getattr(original_builder, "_loco_timeline_context_scope_installed", False):
        return original_builder
    _build_context_scoped_segments._loco_timeline_context_scope_installed = True
    timeline.build_loco_timeline_segments = _build_context_scoped_segments
    return original_builder


def restore_loco_timeline_context_scope_runtime(original_builder: Callable | None) -> None:
    if original_builder is None:
        return
    timeline.build_loco_timeline_segments = original_builder
