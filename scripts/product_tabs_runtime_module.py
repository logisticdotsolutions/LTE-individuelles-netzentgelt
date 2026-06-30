from __future__ import annotations

from typing import Sequence

import loco_timeline_calendar_runtime_module as timeline
import waterfall_overview_runtime_module as waterfall

LOCO_TAB_LABEL = "4. Lok prüfen"
WATERFALL_TAB_LABEL = "5. Wasserfall"
TIMELINE_TAB_LABEL = "6. Lok-Zeitachse"
EXPORT_TAB_LABELS = ["5. Exporte erstellen", "6. Exporte erstellen", "7. Exporte erstellen"]
EXPORT_TAB_RENUMBERED_LABEL = "7. Exporte erstellen"


def _visible_tab_labels(labels: Sequence[object]) -> tuple[list[object], int | None, int | None]:
    values = [str(label) for label in labels]
    if WATERFALL_TAB_LABEL in values or TIMELINE_TAB_LABEL in values:
        return list(labels), None, None
    if LOCO_TAB_LABEL not in values:
        return list(labels), None, None

    visible_labels = list(labels)
    loco_index = values.index(LOCO_TAB_LABEL)
    waterfall_index = loco_index + 1
    timeline_index = loco_index + 2
    visible_labels.insert(waterfall_index, WATERFALL_TAB_LABEL)
    visible_labels.insert(timeline_index, TIMELINE_TAB_LABEL)

    current_values = [str(label) for label in visible_labels]
    for export_label in EXPORT_TAB_LABELS:
        if export_label in current_values:
            visible_labels[current_values.index(export_label)] = EXPORT_TAB_RENUMBERED_LABEL
            break

    return visible_labels, waterfall_index, timeline_index


def install_product_tabs_runtime():
    """Add product tabs in one st.tabs patch to avoid nested tab label mutations on rerun."""
    import streamlit as st

    original_tabs = st.tabs
    if getattr(original_tabs, "_product_tabs_runtime_installed", False):
        return original_tabs

    def patched_tabs(labels: Sequence[object], *args, **kwargs):
        visible_labels, waterfall_index, timeline_index = _visible_tab_labels(labels)
        if waterfall_index is None or timeline_index is None:
            return original_tabs(labels, *args, **kwargs)

        rendered_tabs = list(original_tabs(visible_labels, *args, **kwargs))
        if 0 <= waterfall_index < len(rendered_tabs):
            with rendered_tabs[waterfall_index]:
                waterfall.render_waterfall_overview()
        if 0 <= timeline_index < len(rendered_tabs):
            with rendered_tabs[timeline_index]:
                timeline.render_loco_timeline_calendar()

        inserted_indices = {waterfall_index, timeline_index}
        return [tab for index, tab in enumerate(rendered_tabs) if index not in inserted_indices]

    patched_tabs._product_tabs_runtime_installed = True
    st.tabs = patched_tabs
    return original_tabs


def restore_product_tabs_runtime(original_tabs) -> None:
    if original_tabs is None:
        return
    import streamlit as st

    st.tabs = original_tabs
