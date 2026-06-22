from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import streamlit as st


REMOVE_REVIEW_TAB_MARKER = "NETZENTGELT_REMOVE_REVIEW_TAB_PHASE11R_V1_20260618"
_REVIEW_TAB_LABEL = "6. Weitere Prüfungen"


@contextmanager
def _empty_context() -> Iterator[None]:
    yield None


def install_remove_review_tab_runtime():
    """Hide the obsolete '6. Weitere Prüfungen' tab and disable its renderer."""
    try:
        import phase6d_controller_review_ui as review_ui

        def _noop_render_phase6d_review_lists(*args, **kwargs):
            return None

        review_ui.render_phase6d_review_lists = _noop_render_phase6d_review_lists
    except Exception:
        pass

    original_tabs = st.tabs

    def tabs_without_review(labels, *args, **kwargs):
        values = list(labels)
        if _REVIEW_TAB_LABEL not in values:
            return original_tabs(labels, *args, **kwargs)
        index = values.index(_REVIEW_TAB_LABEL)
        visible = values[:index] + values[index + 1:]
        containers = list(original_tabs(visible, *args, **kwargs))
        containers.insert(index, _empty_context())
        return containers

    st.tabs = tabs_without_review
    return original_tabs


def restore_remove_review_tab_runtime(original_tabs) -> None:
    if original_tabs is not None:
        st.tabs = original_tabs
