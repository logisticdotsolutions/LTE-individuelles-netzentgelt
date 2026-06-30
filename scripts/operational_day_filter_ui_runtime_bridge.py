"""Render the operational day filter early without changing fachliche filtering."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Callable

import streamlit as st

import operational_day_filter_module as operational_day_filter


PHASE11G_EARLY_DAY_FILTER_MARKER = "NETZENTGELT_EARLY_OPERATIONAL_DAY_FILTER_PHASE11G_V1_20260612"
OperationalDayFilterRenderer = Callable[[], tuple[date, date]]
EARLY_RENDER_FLAG = "_operational_day_filter_rendered_early"


def render_early_sidebar_operational_day_filter() -> tuple[date, date]:
    """Render a compact day filter before the verbose legacy sidebar sections."""
    default_day = operational_day_filter.default_operational_day()
    st.sidebar.divider()
    st.sidebar.header("Arbeitszeitraum")
    st.sidebar.caption(
        "Gilt zentral für alle Prüfansichten. Vollständige Kalendertage; "
        "Uhrzeiten werden ignoriert."
    )
    date_from = st.sidebar.date_input(
        "Von-Tag",
        value=default_day,
        key="operational_day_filter_from",
    )
    date_to = st.sidebar.date_input(
        "Bis-Tag",
        value=default_day,
        key="operational_day_filter_to",
    )
    st.session_state[EARLY_RENDER_FLAG] = True
    normalized_from, normalized_to = operational_day_filter.normalize_day_range(
        date_from,
        date_to,
    )
    if (date_from, date_to) != (normalized_from, normalized_to):
        st.sidebar.warning("Von- und Bis-Tag wurden automatisch sortiert.")
    st.sidebar.caption(
        f"Aktiv: {normalized_from:%d.%m.%Y} 00:00 bis "
        f"{(normalized_to + timedelta(days=1)):%d.%m.%Y} 00:00"
    )
    return normalized_from, normalized_to


def install_operational_day_filter_runtime(
    selected_range: tuple[date, date],
) -> OperationalDayFilterRenderer:
    """Return the already rendered range when the legacy app requests its filter."""
    original_renderer = operational_day_filter.render_sidebar_operational_day_filter
    normalized_range = operational_day_filter.normalize_day_range(*selected_range)

    def _return_pre_rendered_range() -> tuple[date, date]:
        return normalized_range

    operational_day_filter.render_sidebar_operational_day_filter = _return_pre_rendered_range
    return original_renderer


def restore_operational_day_filter_runtime(
    original_renderer: OperationalDayFilterRenderer,
) -> None:
    """Restore the legacy renderer after the authenticated app run."""
    operational_day_filter.render_sidebar_operational_day_filter = original_renderer
