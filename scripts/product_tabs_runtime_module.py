from __future__ import annotations

from collections.abc import Callable
from typing import Sequence

import loco_timeline_calendar_runtime_module as timeline
import waterfall_overview_runtime_module as waterfall
from no_lte_assignment_policy_runtime_module import install_no_lte_assignment_policy_runtime
from timeline_event_color_policy_runtime_module import install_timeline_event_color_policy_runtime

LOCO_TAB_LABEL = "4. Lok prüfen"
WATERFALL_TAB_LABEL = "5. Wasserfall"
TIMELINE_TAB_LABEL = "6. Lok-Zeitachse"
EXPORT_TAB_LABELS = ["5. Exporte erstellen", "6. Exporte erstellen", "7. Exporte erstellen"]
EXPORT_TAB_RENUMBERED_LABEL = "7. Exporte erstellen"
TECH_TAB_LABEL = "⚙️ Technik"
_PRODUCT_TABS_ORIGINAL = None
_PRODUCT_TABS_PATCHED = None


def _is_export_label(label: object) -> bool:
    text = str(label).strip()
    if "." in text:
        text = text.split(".", 1)[1].strip()
    return text == "Exporte erstellen"


def _is_tech_label(label: object) -> bool:
    return str(label).replace("\ufe0f", "").strip() == "⚙ Technik"


def _is_managed_product_label(label: object) -> bool:
    text = str(label)
    return text in {WATERFALL_TAB_LABEL, TIMELINE_TAB_LABEL} or _is_export_label(text) or _is_tech_label(text)


def _visible_tab_labels(labels: Sequence[object]) -> tuple[list[object], int | None, int | None]:
    values = [str(label) for label in labels]
    if LOCO_TAB_LABEL not in values:
        return list(labels), None, None

    visible_labels = [label for label in labels if not _is_managed_product_label(label)]
    visible_values = [str(label) for label in visible_labels]
    loco_index = visible_values.index(LOCO_TAB_LABEL)
    waterfall_index = loco_index + 1
    timeline_index = loco_index + 2
    visible_labels.insert(waterfall_index, WATERFALL_TAB_LABEL)
    visible_labels.insert(timeline_index, TIMELINE_TAB_LABEL)
    visible_labels.insert(timeline_index + 1, EXPORT_TAB_RENUMBERED_LABEL)
    visible_labels.insert(timeline_index + 2, TECH_TAB_LABEL)

    return visible_labels, waterfall_index, timeline_index


def _render_injected_tab(tab: object, title: str, render_func: Callable[[], None]) -> None:
    import streamlit as st

    with tab:
        try:
            render_func()
        except Exception as exc:
            st.error(f"{title} konnte nicht gerendert werden: {exc}")


def install_product_tabs_runtime():
    """Add product tabs in one st.tabs patch to avoid nested tab label mutations on rerun."""
    global _PRODUCT_TABS_ORIGINAL, _PRODUCT_TABS_PATCHED

    import streamlit as st

    install_no_lte_assignment_policy_runtime()
    install_timeline_event_color_policy_runtime()
    if _PRODUCT_TABS_PATCHED is not None or getattr(st.tabs, "_product_tabs_runtime_installed", False):
        return _PRODUCT_TABS_ORIGINAL or getattr(st.tabs, "_product_tabs_original", None)

    original_tabs = st.tabs

    def patched_tabs(labels: Sequence[object], *args, **kwargs):
        visible_labels, waterfall_index, timeline_index = _visible_tab_labels(labels)
        if waterfall_index is None or timeline_index is None:
            return original_tabs(visible_labels, *args, **kwargs)

        rendered_tabs = list(original_tabs(visible_labels, *args, **kwargs))
        if 0 <= waterfall_index < len(rendered_tabs):
            _render_injected_tab(
                rendered_tabs[waterfall_index],
                WATERFALL_TAB_LABEL,
                waterfall.render_waterfall_overview,
            )
        if 0 <= timeline_index < len(rendered_tabs):
            _render_injected_tab(
                rendered_tabs[timeline_index],
                TIMELINE_TAB_LABEL,
                timeline.render_loco_timeline_calendar,
            )

        inserted_indices = {waterfall_index, timeline_index}
        return [tab for index, tab in enumerate(rendered_tabs) if index not in inserted_indices]

    patched_tabs._product_tabs_runtime_installed = True
    patched_tabs._product_tabs_original = original_tabs
    _PRODUCT_TABS_ORIGINAL = original_tabs
    _PRODUCT_TABS_PATCHED = patched_tabs
    st.tabs = patched_tabs
    return original_tabs


def restore_product_tabs_runtime(original_tabs) -> None:
    global _PRODUCT_TABS_ORIGINAL, _PRODUCT_TABS_PATCHED

    original_tabs = original_tabs or _PRODUCT_TABS_ORIGINAL
    if original_tabs is None:
        return
    import streamlit as st

    st.tabs = original_tabs
    _PRODUCT_TABS_ORIGINAL = None
    _PRODUCT_TABS_PATCHED = None
