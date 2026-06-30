from __future__ import annotations

from datetime import date, timedelta
from html import escape
from typing import Callable

import pandas as pd

import loco_timeline_calendar_runtime_module as timeline


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


def _axis_labels(visible_from: date, visible_to: date) -> str:
    days = (visible_to - visible_from).days + 1
    if days <= 1:
        return '<div class="hour-labels"><span>00:00</span><span>06:00</span><span>12:00</span><span>18:00</span><span style="text-align:right">24:00</span></div>'

    labels = []
    for index in range(days):
        current = visible_from + timedelta(days=index)
        labels.append(f'<span>{current:%d.%m.}</span>')
    return (
        f'<div class="date-labels" style="grid-template-columns: repeat({days}, 1fr);">'
        + "".join(labels)
        + "</div>"
    )


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
    .loco-day-grid {position:absolute; inset:0; pointer-events:none;}
    .loco-day-grid-line {position:absolute; top:0; bottom:0; width:1px; background:rgba(49,51,63,.16);}
    .loco-segment {position:absolute; top:4px; height:20px; border-radius:6px; border:1px solid rgba(0,0,0,.20); min-width:3px;}
    .status-check {background:#d62728;}
    .status-overlap {background:#ffbf00;}
    .status-gap {background:#ff7f0e;}
    .status-assigned {background:#2ca02c;}
    .status-in-de {background:#1f77b4;}
    .status-outside {background:#9aa0a6;}
    .context-muted {opacity:.46;}
    .hour-labels {display:grid; grid-template-columns: repeat(5, 1fr); font-size:.68rem; color:rgba(49,51,63,.72); margin-left:270px; padding-left:.75rem;}
    .date-labels {display:grid; font-size:.68rem; color:rgba(49,51,63,.72); margin-left:270px; padding-left:.75rem;}
    .loco-axis-note {font-size:.78rem; color:rgba(49,51,63,.74); margin:.25rem 0 .35rem 270px;}
    </style>
    """


def build_loco_multiday_axis_html(
    segments_df: pd.DataFrame,
    *,
    date_from: date,
    date_to: date,
    context_days: int = 1,
    max_rows: int = 140,
) -> str:
    """Render one continuous timeline row per locomotive over the visible date window."""
    if segments_df.empty:
        return "<p>Keine Zeitachsen-Segmente für die aktuelle Auswahl.</p>"

    date_from, date_to = timeline._normalize_day_range(date_from, date_to)
    visible_from, visible_to = _visible_window(date_from, date_to, context_days)
    visible_days = (visible_to - visible_from).days + 1
    total_minutes = max(visible_days * 24 * 60, 1)

    rows_html: list[str] = [_timeline_css(), '<div class="loco-timeline-wrap">']
    rows_html.append(
        '<div class="loco-timeline-legend">'
        '<span class="loco-timeline-chip"><b style="color:#d62728">■</b> Prüfen</span>'
        '<span class="loco-timeline-chip"><b style="color:#ffbf00">■</b> Overlap</span>'
        '<span class="loco-timeline-chip"><b style="color:#ff7f0e">■</b> GAP</span>'
        '<span class="loco-timeline-chip"><b style="color:#2ca02c">■</b> Zugewiesen</span>'
        '<span class="loco-timeline-chip"><b style="color:#1f77b4">■</b> In DE</span>'
        '<span class="loco-timeline-chip"><b style="color:#9aa0a6">■</b> Außerhalb DE / Kontext</span>'
        '<span class="loco-timeline-chip">Satt = Arbeitszeitraum</span>'
        '<span class="loco-timeline-chip">Transparent = Kontexttag</span>'
        '</div>'
    )
    if visible_days > 1:
        rows_html.append(
            f'<div class="loco-axis-note">Achse: {visible_from:%d.%m.%Y} bis {visible_to:%d.%m.%Y} '
            f'(Arbeitszeitraum {date_from:%d.%m.%Y} bis {date_to:%d.%m.%Y})</div>'
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
        for _, row in group.iterrows():
            start_abs, end_abs = _segment_abs_minutes(row, visible_from)
            left = max(0.0, min(100.0, start_abs / total_minutes * 100.0))
            width = max(0.10, min(100.0 - left, (end_abs - start_abs) / total_minutes * 100.0))
            css_class = timeline.STATUS_CSS_CLASS.get(str(row["Status"]), "status-outside")
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
            f'<p style="font-size:.8rem; opacity:.75;">Weitere {len(grouped) - max_rows} Loks ausgeblendet. Bitte stärker filtern.</p>'
        )
    rows_html.append("</div>")
    return "".join(rows_html)


def install_loco_timeline_multiday_axis_runtime() -> Callable | None:
    original_renderer = timeline.render_loco_timeline_calendar
    if getattr(original_renderer, "_loco_timeline_multiday_axis_installed", False):
        return original_renderer

    def patched_render_loco_timeline_calendar() -> None:
        import streamlit as st
        import streamlit.components.v1 as components

        st.header("📅 Lok-Zeitachse")
        st.caption(
            "Kalenderartige Prüfoberfläche je Lok: zugewiesen, GAP, Overlap, "
            "Prüffall, DE-Bezug und Kontext außerhalb des gewählten Zeitraums."
        )

        date_from, date_to = timeline._get_selected_day_range()
        st.info(
            f"Aktiver Arbeitszeitraum: {date_from:%d.%m.%Y} bis {date_to:%d.%m.%Y}. "
            "Für den Kontext wird automatisch jeweils ein Tag davor und danach mitgeladen."
        )

        source_df = timeline._read_csv_safe(timeline.TIMELINE_PATH)
        if source_df.empty:
            st.warning("Keine core_loco_timeline.csv gefunden. Bitte zuerst die Tagesprüfung ausführen.")
            return

        segments = timeline.build_loco_timeline_segments(source_df, date_from=date_from, date_to=date_to, context_days=1)
        if segments.empty:
            st.info("Im gewählten Zeitraum und Kontext wurden keine Lok-Zeitachsen gefunden.")
            return

        summary = timeline.build_loco_timeline_day_summary(segments)
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
            selected_holder = st.selectbox("Halter", ["Alle"] + timeline._options(segments, "Halter"), key="loco_timeline_holder")
        with filter_2:
            selected_performing_ru = st.selectbox(
                "Nutzer / PerformingRU",
                ["Alle"] + timeline._options(segments, "Nutzer / PerformingRU"),
                key="loco_timeline_performing_ru",
            )
        with filter_3:
            selected_status = st.selectbox("Status", ["Alle"] + timeline._options(segments, "Status"), key="loco_timeline_status")
        with filter_4:
            loco_query = st.text_input("Loknummer enthält", key="loco_timeline_loco_query")
        with filter_5:
            only_problem_cases = st.checkbox("Nur Probleme", value=False, key="loco_timeline_only_problems")

        filtered = timeline.filter_loco_timeline_segments(
            segments,
            holder=selected_holder,
            performing_ru=selected_performing_ru,
            status=selected_status,
            loco_query=loco_query,
            only_problem_cases=only_problem_cases,
        )
        filtered_summary = timeline.build_loco_timeline_day_summary(filtered)

        st.write(
            f"Angezeigte Segmente: **{len(filtered)}** · "
            f"Lok-Tage: **{len(filtered_summary)}**"
        )

        if date_from == date_to:
            html = timeline.timeline_segments_to_html(filtered, max_rows=140)
            height_rows = len(filtered_summary)
        else:
            html = build_loco_multiday_axis_html(
                filtered,
                date_from=date_from,
                date_to=date_to,
                context_days=1,
                max_rows=140,
            )
            height_rows = filtered["Loknummer"].nunique() if not filtered.empty else 0
        height = min(920, max(260, 145 + int(height_rows) * 52))
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
            xlsx = timeline.build_loco_timeline_xlsx(filtered, filtered_summary)
            st.download_button(
                "Lok-Zeitachse als XLSX herunterladen",
                data=xlsx,
                file_name=f"lok_zeitachse_{date_from.isoformat()}_bis_{date_to.isoformat()}_plus_kontext.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="download_loco_timeline_calendar_xlsx",
                use_container_width=True,
            )

    patched_render_loco_timeline_calendar._loco_timeline_multiday_axis_installed = True
    timeline.render_loco_timeline_calendar = patched_render_loco_timeline_calendar
    return original_renderer


def restore_loco_timeline_multiday_axis_runtime(original_renderer: Callable | None) -> None:
    if original_renderer is None:
        return
    timeline.render_loco_timeline_calendar = original_renderer
