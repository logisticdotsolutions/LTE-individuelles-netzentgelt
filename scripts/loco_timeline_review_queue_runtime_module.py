from __future__ import annotations

from typing import Sequence

import pandas as pd

from loco_timeline_calendar_runtime_module import (
    TIMELINE_PATH,
    _get_selected_day_range,
    _read_csv_safe,
    build_loco_timeline_segments,
)
from loco_timeline_review_queue_module import PROBLEM_STATUSES, build_loco_timeline_review_queue

TIMELINE_TAB_LABEL = "6. Lok-Zeitachse"
REVIEW_QUEUE_TAB_LABEL = "7. Pruefqueue"
EXPORT_TAB_LABELS = ["7. Exporte erstellen", "6. Exporte erstellen", "5. Exporte erstellen"]
EXPORT_TAB_RENUMBERED_LABEL = "8. Exporte erstellen"


def _load_segments_for_active_period() -> tuple[object, object, pd.DataFrame]:
    date_from, date_to = _get_selected_day_range()
    source_df = _read_csv_safe(TIMELINE_PATH)
    if source_df.empty:
        return date_from, date_to, pd.DataFrame()
    segments = build_loco_timeline_segments(
        source_df,
        date_from=date_from,
        date_to=date_to,
        context_days=1,
    )
    return date_from, date_to, segments


def _detail_rows_for_selection(segments_df: pd.DataFrame, selected_row: pd.Series) -> pd.DataFrame:
    detail_mask = (
        segments_df["Meldetag"].eq(selected_row["Meldetag"])
        & segments_df["Loknummer"].eq(selected_row["Loknummer"])
        & segments_df["Status"].isin(PROBLEM_STATUSES)
    )
    detail_columns = [
        "Meldetag",
        "Loknummer",
        "Halter",
        "Nutzer / PerformingRU",
        "Status",
        "Uhrzeit von",
        "Uhrzeit bis",
        "TransportNumber",
        "Regeln",
        "Meldung",
        "Begründung",
    ]
    return segments_df.loc[detail_mask, detail_columns].reset_index(drop=True)


def render_loco_timeline_review_queue() -> None:
    import streamlit as st

    st.header("Pruefqueue fuer Lok-Zeitachse")
    st.caption(
        "Schnellnavigation ueber problematische Lok-Tage im aktiven Arbeitszeitraum. "
        "Die Queue nutzt dieselbe Zeitachsenlogik inklusive plus/minus einem Kontexttag."
    )

    date_from, date_to, segments = _load_segments_for_active_period()
    st.info(f"Aktiver Arbeitszeitraum: {date_from:%d.%m.%Y} bis {date_to:%d.%m.%Y} · Kontext: +/- 1 Tag")

    if segments.empty:
        st.warning("Keine Zeitachsen-Segmente gefunden. Bitte zuerst die Tagespruefung ausfuehren.")
        return

    review_queue = build_loco_timeline_review_queue(segments)
    if review_queue.empty:
        st.success("Keine problematischen Lok-Tage im aktuellen Zeitraum gefunden.")
        return

    metric_1, metric_2, metric_3, metric_4 = st.columns(4)
    with metric_1:
        st.metric("Problem-Lok-Tage", int(len(review_queue)))
    with metric_2:
        st.metric("Pruefen", int((review_queue["Status"] == "Prüfen").sum()))
    with metric_3:
        st.metric("Overlap", int((review_queue["Status"] == "Overlap").sum()))
    with metric_4:
        st.metric("GAP", int((review_queue["Status"] == "GAP").sum()))

    selected_case = st.selectbox(
        "Problemfall auswaehlen",
        review_queue["Auswahl"].tolist(),
        key="loco_timeline_review_queue_case",
    )
    selected_row = review_queue[review_queue["Auswahl"].eq(selected_case)].iloc[0]
    st.warning(
        f"{selected_row['Status']} · Lok {selected_row['Loknummer']} · "
        f"{selected_row['Meldetag']} · {selected_row['Erste Uhrzeit']} bis {selected_row['Letzte Uhrzeit']}"
    )

    st.markdown("#### Betroffene Segmente")
    st.dataframe(
        _detail_rows_for_selection(segments, selected_row),
        use_container_width=True,
        hide_index=True,
        height=260,
    )

    with st.expander("Gesamte Pruefqueue", expanded=False):
        st.dataframe(review_queue, use_container_width=True, hide_index=True, height=520)

    csv = review_queue.to_csv(index=False, sep=";").encode("utf-8-sig")
    st.download_button(
        "Pruefqueue als CSV herunterladen",
        data=csv,
        file_name=f"lok_zeitachse_pruefqueue_{date_from.isoformat()}_bis_{date_to.isoformat()}_plus_kontext.csv",
        mime="text/csv",
        key="download_loco_timeline_review_queue_csv",
        use_container_width=True,
    )


def _visible_tab_labels(labels: Sequence[object]) -> tuple[list[object], int | None]:
    values = [str(label) for label in labels]
    if REVIEW_QUEUE_TAB_LABEL in values or TIMELINE_TAB_LABEL not in values:
        return list(labels), None

    visible_labels = list(labels)
    review_index = values.index(TIMELINE_TAB_LABEL) + 1
    visible_labels.insert(review_index, REVIEW_QUEUE_TAB_LABEL)

    current_values = [str(label) for label in visible_labels]
    for export_label in EXPORT_TAB_LABELS:
        if export_label in current_values:
            visible_labels[current_values.index(export_label)] = EXPORT_TAB_RENUMBERED_LABEL
            break
    return visible_labels, review_index


def install_loco_timeline_review_queue_runtime():
    import streamlit as st

    original_tabs = st.tabs
    if getattr(original_tabs, "_loco_timeline_review_queue_installed", False):
        return original_tabs

    def patched_tabs(labels: Sequence[object], *args, **kwargs):
        visible_labels, review_index = _visible_tab_labels(labels)
        if review_index is None:
            return original_tabs(labels, *args, **kwargs)
        rendered_tabs = list(original_tabs(visible_labels, *args, **kwargs))
        if 0 <= review_index < len(rendered_tabs):
            with rendered_tabs[review_index]:
                render_loco_timeline_review_queue()
            return rendered_tabs[:review_index] + rendered_tabs[review_index + 1:]
        return rendered_tabs

    patched_tabs._loco_timeline_review_queue_installed = True
    st.tabs = patched_tabs
    return original_tabs


def restore_loco_timeline_review_queue_runtime(original_tabs) -> None:
    if original_tabs is None:
        return
    import streamlit as st

    st.tabs = original_tabs
