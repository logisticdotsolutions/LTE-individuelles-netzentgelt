from __future__ import annotations

from datetime import date, datetime, time, timedelta
from html import escape
from typing import Callable

import pandas as pd

from broken_route_chain_policy_module import is_no_lte_assignment_marker
import loco_timeline_calendar_runtime_module as timeline
import loco_timeline_detail_dropdown_runtime_module as detail_dropdown
import loco_timeline_multiday_axis_runtime_module as multiday_axis
from no_lte_assignment_policy_runtime_module import is_outside_report_marker

PROBLEM_STATUSES = {"Prüfen", "Overlap", "GAP"}
ASSIGNED_STATUSES = {"Zugewiesen", "In DE"}
NORMAL_MOVEMENT_STATUSES = {"Zugewiesen", "In DE", "Außerhalb DE"}
NOT_IN_REPORT_VISUAL_STATUS = "Not in the report"
NO_LTE_VISUAL_STATUS = "Keine LTE Zuordnung"
MINUTES_PER_DAY = 24 * 60
EVENT_VISUAL_STATUS_BY_LABEL = {
    "in de": "In DE",
    "einfahrt": "Einfahrt",
    "ausfahrt": "Ausfahrt",
    "einfahrt + ausfahrt": "Einfahrt + Ausfahrt",
    "ausserhalb de": "Außerhalb DE",
    "außerhalb de": "Außerhalb DE",
}


# NETZENTGELT_TIMELINE_EVENT_COLOR_PATCH_MARKER_V1_20260701

def _visible_window(date_from: date, date_to: date, context_days: int) -> tuple[date, date]:
    date_from, date_to = timeline._normalize_day_range(date_from, date_to)
    context_days = max(int(context_days), 0)
    return date_from - timedelta(days=context_days), date_to + timedelta(days=context_days)


def _segment_abs_minutes(row: pd.Series, visible_from: date) -> tuple[int, int]:
    day = pd.Timestamp(str(row["Meldetag"])).date()
    day_offset = (day - visible_from).days * MINUTES_PER_DAY
    start_minute = day_offset + int(row["StartMinute"])
    end_minute = day_offset + int(row["EndMinute"])
    return start_minute, max(start_minute + 1, end_minute)


def _clean_text(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value or "").strip()


def _row_text(row: pd.Series, *columns: str) -> str:
    for column in columns:
        if column in row.index:
            value = _clean_text(row.get(column, ""))
            if value:
                return value
    return ""


def _row_values(row: pd.Series, *columns: str) -> list[str]:
    return [_clean_text(row.get(column, "")) for column in columns if column in row.index]


def _visual_status_from_event(row: pd.Series) -> str | None:
    event_label = _row_text(row, "Event Type", "de_event_label")
    normalized = event_label.casefold().replace("_", " ").replace("ß", "ss")
    return EVENT_VISUAL_STATUS_BY_LABEL.get(normalized)


def _is_hard_not_in_report_row(row: pd.Series) -> bool:
    hard_values = _row_values(
        row,
        "report_scope",
        "Report-Scope",
        "row_type",
        "Row Type",
        "Status",
    )
    return is_outside_report_marker(*hard_values)


def _has_route_fallback_without_event(row: pd.Series) -> bool:
    route_values = _row_values(row, "Route Type", "cal_route_type_home")
    normalized_values = {value.casefold().replace("_", " ") for value in route_values}
    return bool(normalized_values & {"kein bezug", "kein lte bezug"})


def _has_no_lte_assignment_marker(row: pd.Series) -> bool:
    marker_values = _row_values(
        row,
        "Status",
        "Event Type",
        "de_event_label",
        "Halter",
        "holder_name",
        "Nutzer / PerformingRU",
        "performing_ru",
        "Regeln",
    )
    return is_no_lte_assignment_marker(*marker_values)


def _is_no_lte_without_positive_event(row: pd.Series) -> bool:
    return _has_no_lte_assignment_marker(row) or _has_route_fallback_without_event(row)


def _derive_visual_status(row: pd.Series) -> str:
    status = _row_text(row, "Status") or "Außerhalb DE"
    event_status = _visual_status_from_event(row)

    if _is_hard_not_in_report_row(row):
        return NOT_IN_REPORT_VISUAL_STATUS

    if status in PROBLEM_STATUSES:
        return status

    if event_status:
        return event_status

    if _is_no_lte_without_positive_event(row):
        return NO_LTE_VISUAL_STATUS

    if status in ASSIGNED_STATUSES:
        return "Zugewiesen" if status == "Zugewiesen" else "In DE"
    return status or "Außerhalb DE"


def _visual_css_class(visual_status: str) -> str:
    return timeline.STATUS_CSS_CLASS.get(str(visual_status), "status-outside")


def _band_from_row(
    row: pd.Series,
    *,
    start_abs: int,
    end_abs: int,
    status: str,
    visual_status: str,
) -> dict[str, object]:
    return {
        "start": start_abs,
        "end": end_abs,
        "status": status,
        "visual_status": visual_status,
        "css_class": _visual_css_class(visual_status),
        "in_filter": bool(row.get("Im Filterzeitraum", True)),
        "tooltip": str(row.get("Tooltip", "")),
    }


def _minute_label(visible_from: date, minute: int) -> str:
    timestamp = datetime.combine(visible_from, time.min) + timedelta(minutes=int(minute))
    return timestamp.strftime("%d.%m.%Y %H:%M")


def _active_window_minutes(visible_from: date, date_from: date, date_to: date) -> tuple[int, int]:
    date_from, date_to = timeline._normalize_day_range(date_from, date_to)
    active_start = (date_from - visible_from).days * MINUTES_PER_DAY
    active_end = (date_to + timedelta(days=1) - visible_from).days * MINUTES_PER_DAY
    return active_start, active_end


def _fill_tooltip(visible_from: date, start_minute: int, end_minute: int, visual_status: str) -> str:
    return (
        "Automatisch gefüllter Zeitraum: "
        f"{_minute_label(visible_from, start_minute)} bis {_minute_label(visible_from, end_minute)}. "
        f"Visualstatus: {visual_status}."
    )


def _fill_band(
    *,
    visible_from: date,
    start_minute: int,
    end_minute: int,
    visual_status: str,
    in_filter: bool,
) -> dict[str, object]:
    return {
        "start": int(start_minute),
        "end": int(end_minute),
        "status": visual_status,
        "visual_status": visual_status,
        "css_class": _visual_css_class(visual_status),
        "in_filter": bool(in_filter),
        "tooltip": _fill_tooltip(visible_from, start_minute, end_minute, visual_status),
        "auto_fill": True,
    }


def _iter_fill_ranges(
    start_minute: int,
    end_minute: int,
    *,
    visible_from: date,
    date_from: date,
    date_to: date,
) -> list[dict[str, object]]:
    active_start, active_end = _active_window_minutes(visible_from, date_from, date_to)
    boundaries = {int(start_minute), int(end_minute)}
    if start_minute < active_start < end_minute:
        boundaries.add(active_start)
    if start_minute < active_end < end_minute:
        boundaries.add(active_end)

    ranges: list[dict[str, object]] = []
    ordered = sorted(boundaries)
    for range_start, range_end in zip(ordered, ordered[1:]):
        if range_end <= range_start:
            continue
        in_filter = range_start < active_end and range_end > active_start
        visual_status = NO_LTE_VISUAL_STATUS if in_filter else NOT_IN_REPORT_VISUAL_STATUS
        ranges.append(
            _fill_band(
                visible_from=visible_from,
                start_minute=range_start,
                end_minute=range_end,
                visual_status=visual_status,
                in_filter=in_filter,
            )
        )
    return ranges


def _fill_visual_band_gaps(
    bands: list[dict[str, object]],
    *,
    visible_start_minute: int,
    visible_end_minute: int,
    visible_from: date,
    date_from: date,
    date_to: date,
) -> list[dict[str, object]]:
    """Fill the visible axis with derived visual bands without changing source bands."""
    window_start = int(visible_start_minute)
    window_end = max(window_start, int(visible_end_minute))
    if window_end <= window_start:
        return []

    clipped_bands: list[tuple[int, int, dict[str, object]]] = []
    for band in bands:
        start_minute = max(window_start, int(band["start"]))
        end_minute = min(window_end, int(band["end"]))
        if end_minute > start_minute:
            clipped_bands.append((start_minute, end_minute, band))

    filled: list[dict[str, object]] = []
    cursor = window_start
    for start_minute, end_minute, band in sorted(clipped_bands, key=lambda item: (item[0], item[1])):
        if start_minute > cursor:
            filled.extend(
                _iter_fill_ranges(
                    cursor,
                    start_minute,
                    visible_from=visible_from,
                    date_from=date_from,
                    date_to=date_to,
                )
            )

        render_start = max(start_minute, cursor)
        if end_minute <= render_start:
            continue

        render_band = dict(band)
        render_band["start"] = render_start
        render_band["end"] = end_minute
        filled.append(render_band)
        cursor = max(cursor, end_minute)

    if cursor < window_end:
        filled.extend(
            _iter_fill_ranges(
                cursor,
                window_end,
                visible_from=visible_from,
                date_from=date_from,
                date_to=date_to,
            )
        )

    return filled


def build_loco_visual_bands(group: pd.DataFrame, *, visible_from: date) -> list[dict[str, object]]:
    """Build fachliche visual bands from movement fragments for one locomotive."""
    if group.empty:
        return []

    work = group.copy()
    starts = []
    ends = []
    for _, row in work.iterrows():
        start_abs, end_abs = _segment_abs_minutes(row, visible_from)
        starts.append(start_abs)
        ends.append(end_abs)
    work["_abs_start"] = starts
    work["_abs_end"] = ends
    work = work.sort_values(
        by=["_abs_start", "StatusPriorität", "_abs_end"],
        ascending=[True, False, True],
        kind="stable",
    ).reset_index(drop=True)

    visual_bands: list[dict[str, object]] = []
    current_assignment: dict[str, object] | None = None

    def close_assignment(until_minute: int | None = None) -> None:
        nonlocal current_assignment
        if current_assignment is None:
            return
        if until_minute is not None:
            current_assignment["end"] = min(int(current_assignment["end"]), int(until_minute))
        if int(current_assignment["end"]) > int(current_assignment["start"]):
            visual_bands.append(current_assignment)
        current_assignment = None

    for _, row in work.iterrows():
        status = str(row.get("Status", ""))
        start_abs = int(row["_abs_start"])
        end_abs = int(row["_abs_end"])
        visual_status = _derive_visual_status(row)

        if status in PROBLEM_STATUSES:
            close_assignment(start_abs)
            visual_bands.append(
                _band_from_row(
                    row,
                    start_abs=start_abs,
                    end_abs=end_abs,
                    status=status,
                    visual_status=visual_status,
                )
            )
            continue

        if status in NORMAL_MOVEMENT_STATUSES or visual_status in timeline.STATUS_CSS_CLASS:
            assignment_status = "Zugewiesen" if status == "Zugewiesen" else status or "Außerhalb DE"
            if current_assignment is None:
                current_assignment = _band_from_row(
                    row,
                    start_abs=start_abs,
                    end_abs=end_abs,
                    status=assignment_status,
                    visual_status=visual_status,
                )
            else:
                if str(current_assignment.get("visual_status", "")) != visual_status:
                    close_assignment(start_abs)
                    current_assignment = _band_from_row(
                        row,
                        start_abs=start_abs,
                        end_abs=end_abs,
                        status=assignment_status,
                        visual_status=visual_status,
                    )
                    continue
                current_assignment["end"] = max(int(current_assignment["end"]), end_abs)
                if assignment_status == "Zugewiesen":
                    current_assignment["status"] = "Zugewiesen"
                current_assignment["in_filter"] = bool(current_assignment["in_filter"]) or bool(
                    row.get("Im Filterzeitraum", True)
                )
                title = str(row.get("Tooltip", ""))
                if title and title not in str(current_assignment["tooltip"]):
                    current_assignment["tooltip"] = f"{current_assignment['tooltip']} | {title}".strip(" |")
            continue

        close_assignment()
        visual_bands.append(
            _band_from_row(
                row,
                start_abs=start_abs,
                end_abs=end_abs,
                status=status or "Außerhalb DE",
                visual_status=visual_status,
            )
        )

    close_assignment()
    return sorted(visual_bands, key=lambda band: (int(band["start"]), int(band["end"])))


def _axis_labels(visible_from: date, visible_to: date) -> str:
    days = (visible_to - visible_from).days + 1
    labels = []
    for index in range(days):
        current = visible_from + timedelta(days=index)
        labels.append(f'<span>{current:%d.%m.}</span>')
    return (
        f'<div class="date-labels" style="grid-template-columns: repeat({days}, 1fr);">'
        + "".join(labels)
        + "</div>"
    )


def build_loco_multiday_axis_html_with_visual_bands(
    segments_df: pd.DataFrame,
    *,
    date_from: date,
    date_to: date,
    context_days: int = 1,
    max_rows: int = 140,
) -> str:
    if segments_df.empty:
        return "<p>Keine Zeitachsen-Segmente für die aktuelle Auswahl.</p>"

    date_from, date_to = timeline._normalize_day_range(date_from, date_to)
    visible_from, visible_to = _visible_window(date_from, date_to, context_days)
    visible_days = (visible_to - visible_from).days + 1
    total_minutes = max(visible_days * 24 * 60, 1)

    rows_html: list[str] = [multiday_axis._timeline_css(), '<div class="loco-timeline-wrap">']
    rows_html.append(
        '<div class="loco-timeline-legend">'
        '<span class="loco-timeline-chip"><b style="color:#d62728">■</b> Prüfen</span>'
        '<span class="loco-timeline-chip"><b style="color:#ffbf00">■</b> Overlap</span>'
        '<span class="loco-timeline-chip"><b style="color:#ff7f0e">■</b> GAP</span>'
        '<span class="loco-timeline-chip"><b style="color:#2ca02c">■</b> Zugewiesen</span>'
        '<span class="loco-timeline-chip"><b style="color:#d9eaf7">■</b> In DE</span>'
        '<span class="loco-timeline-chip"><b style="color:#b7e1cd">■</b> Einfahrt</span>'
        '<span class="loco-timeline-chip"><b style="color:#d9ead3">■</b> Ausfahrt</span>'
        '<span class="loco-timeline-chip"><b style="color:#6b7280">■</b> Keine LTE Zuordnung</span>'
        '<span class="loco-timeline-chip"><b style="color:#9aa0a6">■</b> Außerhalb DE</span>'
        '<span class="loco-timeline-chip"><b style="color:#161a20">■</b> Not in the report</span>'
        '<span class="loco-timeline-chip">Satt = Arbeitszeitraum</span>'
        '<span class="loco-timeline-chip">Transparent = Kontexttag</span>'
        '</div>'
    )
    rows_html.append(
        f'<div class="loco-axis-note">Achse: {visible_from:%d.%m.%Y} bis {visible_to:%d.%m.%Y} '
        f'(Arbeitszeitraum {date_from:%d.%m.%Y} bis {date_to:%d.%m.%Y}) · '
        'Bewegungsfragmente werden nach Eventfarbe zu Nutzungsbändern zusammengezogen, sofern keine GAP-/Prüfzeile dazwischenliegt.</div>'
    )
    rows_html.append(_axis_labels(visible_from, visible_to))

    grid_lines = '<div class="loco-day-grid">' + "".join(
        f'<span class="loco-day-grid-line" style="left:{(index / visible_days) * 100:.4f}%;"></span>'
        for index in range(1, visible_days)
    ) + '</div>'

    grouped = list(segments_df.groupby("Loknummer", sort=True, dropna=False))
    for loco, group in grouped[:max_rows]:
        highest = group.sort_values("StatusPriorität", ascending=False).iloc[0]
        statuses = " | ".join(sorted(set(group["Status"].astype(str))))
        holders = " | ".join(sorted(set(group["Halter"].astype(str))))
        performers = " | ".join(sorted(set(group["Nutzer / PerformingRU"].astype(str))))
        days = " | ".join(sorted(set(group["Meldetag"].astype(str))))
        meta = (
            f'<div class="loco-meta">'
            f'<div class="loco-day">{escape(str(days))}</div>'
            f'<div class="loco-number">{escape(str(loco))}</div>'
            f'<div>{escape(str(highest["Status"]))} · {escape(statuses)}</div>'
            f'<div>Halter: {escape(holders)}</div>'
            f'<div>Nutzer: {escape(performers)}</div>'
            f'</div>'
        )
        segments_html: list[str] = [f'<div class="loco-track">{grid_lines}']
        visual_bands = _fill_visual_band_gaps(
            build_loco_visual_bands(group, visible_from=visible_from),
            visible_start_minute=0,
            visible_end_minute=total_minutes,
            visible_from=visible_from,
            date_from=date_from,
            date_to=date_to,
        )
        for band in visual_bands:
            left = max(0.0, min(100.0, int(band["start"]) / total_minutes * 100.0))
            width = max(0.10, min(100.0 - left, (int(band["end"]) - int(band["start"])) / total_minutes * 100.0))
            visual_status = str(band.get("visual_status", band["status"]))
            css_class = str(band.get("css_class") or timeline.STATUS_CSS_CLASS.get(visual_status, "status-outside"))
            context_class = "" if bool(band.get("in_filter", True)) else " context-muted"
            title = escape(str(band.get("tooltip", "")), quote=True)
            data_status = escape(str(band.get("status", "")), quote=True)
            data_visual_status = escape(visual_status, quote=True)
            segments_html.append(
                f'<div class="loco-segment {css_class}{context_class}" '
                f'data-status="{data_status}" data-visual-status="{data_visual_status}" '
                f'style="left:{left:.4f}%; width:{width:.4f}%;" title="{title}"></div>'
            )
        segments_html.append("</div>")
        rows_html.append(f'<div class="loco-row">{meta}{"".join(segments_html)}</div>')

    if len(grouped) > max_rows:
        rows_html.append(
            f'<p style="font-size:.8rem; opacity:.75;">Weitere {len(grouped) - max_rows} Loks ausgeblendet. Bitte stärker filtern.</p>'
        )
    rows_html.append("</div>")
    return "".join(rows_html)


def install_loco_timeline_visual_band_runtime() -> tuple[Callable | None, Callable | None] | Callable | None:
    original_renderer = multiday_axis.build_loco_multiday_axis_html
    if getattr(original_renderer, "_loco_timeline_visual_band_installed", False):
        return original_renderer
    original_detail_renderer = detail_dropdown.install_loco_timeline_detail_dropdown_runtime()
    build_loco_multiday_axis_html_with_visual_bands._loco_timeline_visual_band_installed = True
    multiday_axis.build_loco_multiday_axis_html = build_loco_multiday_axis_html_with_visual_bands
    return original_renderer, original_detail_renderer


def restore_loco_timeline_visual_band_runtime(original_renderer) -> None:
    if original_renderer is None:
        return
    original_axis_renderer = original_renderer
    original_detail_renderer = None
    if isinstance(original_renderer, tuple):
        original_axis_renderer, original_detail_renderer = original_renderer
    detail_dropdown.restore_loco_timeline_detail_dropdown_runtime(original_detail_renderer)
    if original_axis_renderer is not None:
        multiday_axis.build_loco_multiday_axis_html = original_axis_renderer
