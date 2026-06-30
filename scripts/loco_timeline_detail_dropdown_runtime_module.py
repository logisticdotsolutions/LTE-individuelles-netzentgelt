from __future__ import annotations

from typing import Callable

import pandas as pd

import loco_timeline_calendar_runtime_module as timeline


def _current_filtered_segments() -> pd.DataFrame:
    date_from, date_to = timeline._get_selected_day_range()
    source_df = timeline._read_csv_safe(timeline.TIMELINE_PATH)
    if source_df.empty:
        return timeline.EMPTY_SEGMENTS.copy()

    segments = timeline.build_loco_timeline_segments(
        source_df,
        date_from=date_from,
        date_to=date_to,
        context_days=1,
    )
    if segments.empty:
        return segments

    try:
        import streamlit as st

        holder = st.session_state.get("loco_timeline_holder", "Alle")
        performing_ru = st.session_state.get("loco_timeline_performing_ru", "Alle")
        status = st.session_state.get("loco_timeline_status", "Alle")
        loco_query = st.session_state.get("loco_timeline_loco_query", "")
        only_problem_cases = bool(st.session_state.get("loco_timeline_only_problems", False))
    except Exception:
        holder = "Alle"
        performing_ru = "Alle"
        status = "Alle"
        loco_query = ""
        only_problem_cases = False

    return timeline.filter_loco_timeline_segments(
        segments,
        holder=holder,
        performing_ru=performing_ru,
        status=status,
        loco_query=loco_query,
        only_problem_cases=only_problem_cases,
    )


def render_loco_timeline_detail_dropdown() -> None:
    import streamlit as st

    filtered = _current_filtered_segments()
    if filtered.empty or "Loknummer" not in filtered.columns:
        return

    loco_options = sorted(
        {str(value).strip() for value in filtered["Loknummer"].dropna().tolist() if str(value).strip()}
    )
    if not loco_options:
        return

    st.markdown("#### Lok aus Zeitachse öffnen")
    selected_loco = st.selectbox(
        "Lok auswählen",
        ["Bitte auswählen"] + loco_options,
        key="loco_timeline_detail_dropdown_loco",
    )
    if selected_loco == "Bitte auswählen":
        return

    loco_rows = filtered[filtered["Loknummer"].astype(str).eq(selected_loco)].copy()
    if loco_rows.empty:
        st.info("Für diese Lok sind in der aktuellen Zeitachse keine Segmente sichtbar.")
        return

    summary = timeline.build_loco_timeline_day_summary(loco_rows)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Segmente", int(len(loco_rows)))
    with c2:
        st.metric("Lok-Tage", int(len(summary)))
    with c3:
        st.metric("GAP/Overlap", int(loco_rows["Status"].isin(["GAP", "Overlap"]).sum()))
    with c4:
        st.metric("Außerhalb DE", int(loco_rows["Status"].eq("Außerhalb DE").sum()))

    detail_columns = [
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
    visible_columns = [column for column in detail_columns if column in loco_rows.columns]
    st.dataframe(loco_rows[visible_columns], use_container_width=True, hide_index=True, height=360)


def install_loco_timeline_detail_dropdown_runtime() -> Callable | None:
    original_renderer = timeline.render_loco_timeline_calendar
    if getattr(original_renderer, "_loco_timeline_detail_dropdown_installed", False):
        return original_renderer

    def patched_render_loco_timeline_calendar() -> None:
        original_renderer()
        render_loco_timeline_detail_dropdown()

    patched_render_loco_timeline_calendar._loco_timeline_detail_dropdown_installed = True
    timeline.render_loco_timeline_calendar = patched_render_loco_timeline_calendar
    return original_renderer


def restore_loco_timeline_detail_dropdown_runtime(original_renderer: Callable | None) -> None:
    if original_renderer is None:
        return
    timeline.render_loco_timeline_calendar = original_renderer
