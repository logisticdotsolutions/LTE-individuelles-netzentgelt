from __future__ import annotations

from datetime import date, timedelta
from html import escape
from typing import Callable

import pandas as pd

import loco_timeline_calendar_runtime_module as timeline
import loco_timeline_multiday_axis_runtime_module as multiday_axis

PROBLEM_STATUSES = {"Prüfen", "Overlap", "GAP"}
ASSIGNED_STATUSES = {"Zugewiesen", "In DE"}


def _visible_window(date_from: date, date_to: date, context_days: int) -> tuple[date, date]:
    date_from, date_to = timeline._normalize_day_range(date_from, date_to)
    context_days = max(int(context_days), 0)
    return date_from - timedelta(days=context_days), date_to + timedelta(days=context_days)


def _segment_abs_minutes(row: pd.Series, visible_from: date) -> tuple[int, int]:
    day = pd.Timestamp(str(row["Meldetag"])).date()
    day_offset = (day - visible_from).days * 24 * 60
    start_minute = day_offset + int(row["StartMinute"])
    end_minute = day_offset + int(row["EndMinute"])
    return start_minute, max(start_minute + 1, end_minute)


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
        title = str(row.get("Tooltip", ""))
        in_filter = bool(row.get("Im Filterzeitraum", True))

        if status in PROBLEM_STATUSES:
            close_assignment(start_abs)
            visual_bands.append(
                {
                    "start": start_abs,
                    "end": end_abs,
                    "status": status,
                    "in_filter": in_filter,
                    "tooltip": title,
                }
            )
            continue

        if status in ASSIGNED_STATUSES:
            assignment_status = "Zugewiesen" if status == "Zugewiesen" else "In DE"
            if current_assignment is None:
                current_assignment = {
                    "start": start_abs,
                    "end": end_abs,
                    "status": assignment_status,
                    "in_filter": in_filter,
                    "tooltip": title,
                }
            else:
                current_assignment["end"] = max(int(current_assignment["end"]), end_abs)
                if assignment_status == "Zugewiesen":
                    current_assignment["status"] = "Zugewiesen"
                current_assignment["in_filter"] = bool(current_assignment["in_filter"]) or in_filter
                if title and title not in str(current_assignment["tooltip"]):
                    current_assignment["tooltip"] = f"{current_assignment['tooltip']} | {title}".strip(" |")
            continue

        close_assignment()
        visual_bands.append(
            {
                "start": start_abs,
                "end": end_abs,
                "status": status or "Außerhalb DE",
                "in_filter": in_filter,
                "tooltip": title,
            }
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
        '<span class="loco-timeline-chip"><b style="color:#1f77b4">■</b> In DE</span>'
        '<span class="loco-timeline-chip">Satt = Arbeitszeitraum</span>'
        '<span class="loco-timeline-chip">Transparent = Kontexttag</span>'
        '</div>'
    )
    rows_html.append(
        f'<div class="loco-axis-note">Achse: {visible_from:%d.%m.%Y} bis {visible_to:%d.%m.%Y} '
        f'(Arbeitszeitraum {date_from:%d.%m.%Y} bis {date_to:%d.%m.%Y}) · '
        'Bewegungsfragmente werden zu fachlichen Nutzungsbändern zusammengezogen, sofern keine GAP-/Prüfzeile dazwischenliegt.</div>'
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
        for band in build_loco_visual_bands(group, visible_from=visible_from):
            left = max(0.0, min(100.0, int(band["start"]) / total_minutes * 100.0))
            width = max(0.10, min(100.0 - left, (int(band["end"]) - int(band["start"])) / total_minutes * 100.0))
            css_class = timeline.STATUS_CSS_CLASS.get(str(band["status"]), "status-outside")
            context_class = "" if bool(band.get("in_filter", True)) else " context-muted"
            title = escape(str(band.get("tooltip", "")), quote=True)
            segments_html.append(
                f'<div class="loco-segment {css_class}{context_class}" '
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


def install_loco_timeline_visual_band_runtime() -> Callable | None:
    original_renderer = multiday_axis.build_loco_multiday_axis_html
    if getattr(original_renderer, "_loco_timeline_visual_band_installed", False):
        return original_renderer
    build_loco_multiday_axis_html_with_visual_bands._loco_timeline_visual_band_installed = True
    multiday_axis.build_loco_multiday_axis_html = build_loco_multiday_axis_html_with_visual_bands
    return original_renderer


def restore_loco_timeline_visual_band_runtime(original_renderer: Callable | None) -> None:
    if original_renderer is None:
        return
    multiday_axis.build_loco_multiday_axis_html = original_renderer
