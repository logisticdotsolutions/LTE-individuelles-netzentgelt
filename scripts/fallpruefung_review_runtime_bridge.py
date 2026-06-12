from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import pandas as pd
import streamlit as st

import manual_override_suggestion_module as suggestion_module
import phase6d_controller_review_ui as review_ui


FALL_TAB_LABEL = "3. Fall bearbeiten"
REVIEW_TAB_LABEL = "6. Weitere Prüfungen"
HIDDEN_REVIEW_TAB_LABEL = " "
COLD_STAND_PROPOSAL_MIN_MINUTES = 120


@dataclass
class FallpruefungReviewRuntime:
    """Runtime-Zustand für Fallprüfungsintegration und Vorschlagslogik."""

    original_tabs: object
    original_renderer: object
    original_cold_stand_suggester: object
    original_cold_stand_min_minutes: int
    fall_tab: object | None = None


def _duration_minutes(period_start_utc: object, period_end_utc: object) -> float | None:
    """Zeitspanne eines Vorschlags defensiv in Minuten berechnen."""
    start = pd.to_datetime(period_start_utc, errors="coerce")
    end = pd.to_datetime(period_end_utc, errors="coerce")

    if pd.isna(start) or pd.isna(end):
        return None

    return float((end - start).total_seconds() / 60.0)


def install_fallpruefung_review_integration() -> FallpruefungReviewRuntime:
    """
    Zusätzliche Prüflisten in den Reiter Fall bearbeiten verschieben.

    Zusätzlich wird die regelbasierte Kaltabstellungsmarkierung bewusst als
    prüfpflichtiger Vorschlag ab GAP > 120 Minuten aktiviert. Sie erzeugt keine
    automatische Abstellung und verändert keine Rohdaten.
    """
    runtime = FallpruefungReviewRuntime(
        original_tabs=st.tabs,
        original_renderer=review_ui.render_phase6d_review_lists,
        original_cold_stand_suggester=suggestion_module._suggest_cold_stands,
        original_cold_stand_min_minutes=suggestion_module.COLD_STAND_MIN_MINUTES,
    )

    def strict_cold_stand_suggestions(timeline):
        candidates = runtime.original_cold_stand_suggester(timeline)
        result = []

        for candidate in candidates:
            minutes = _duration_minutes(
                candidate.period_start_utc,
                candidate.period_end_utc,
            )

            if minutes is not None and minutes > COLD_STAND_PROPOSAL_MIN_MINUTES:
                result.append(candidate)

        return result

    def patched_tabs(labels: Sequence[object]):
        normalized_labels = [str(label) for label in labels]

        if FALL_TAB_LABEL not in normalized_labels or REVIEW_TAB_LABEL not in normalized_labels:
            return runtime.original_tabs(labels)

        fall_index = normalized_labels.index(FALL_TAB_LABEL)
        review_index = normalized_labels.index(REVIEW_TAB_LABEL)
        rendered_labels = list(labels)
        rendered_labels[review_index] = HIDDEN_REVIEW_TAB_LABEL
        rendered_tabs = list(runtime.original_tabs(rendered_labels))
        runtime.fall_tab = rendered_tabs[fall_index]

        st.markdown(
            """
            <style>
            /* Der frühere Reiter 'Weitere Prüfungen' bleibt nur als technischer
               Legacy-Platzhalter bestehen und wird in der Hauptnavigation verborgen. */
            [data-testid="stTabs"]:first-of-type
            [data-baseweb="tab-list"] > button:nth-child(6) {
                display: none !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

        return rendered_tabs

    def rerouted_review_renderer(**kwargs) -> None:
        if runtime.fall_tab is None:
            runtime.original_renderer(**kwargs)
            return

        with runtime.fall_tab:
            st.divider()
            runtime.original_renderer(**kwargs)

    suggestion_module.COLD_STAND_MIN_MINUTES = COLD_STAND_PROPOSAL_MIN_MINUTES
    suggestion_module._suggest_cold_stands = strict_cold_stand_suggestions
    st.tabs = patched_tabs
    review_ui.render_phase6d_review_lists = rerouted_review_renderer
    return runtime


def restore_fallpruefung_review_integration(runtime: FallpruefungReviewRuntime) -> None:
    """Streamlit-, Renderer- und Vorschlags-Patches vollständig zurücksetzen."""
    review_ui.render_phase6d_review_lists = runtime.original_renderer
    suggestion_module._suggest_cold_stands = runtime.original_cold_stand_suggester
    suggestion_module.COLD_STAND_MIN_MINUTES = runtime.original_cold_stand_min_minutes
    st.tabs = runtime.original_tabs
