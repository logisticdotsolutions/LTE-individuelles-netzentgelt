from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import streamlit as st

import phase6d_controller_review_ui as review_ui


FALL_TAB_LABEL = "3. Fall bearbeiten"
REVIEW_TAB_LABEL = "6. Weitere Prüfungen"
HIDDEN_REVIEW_TAB_LABEL = " "


@dataclass
class FallpruefungReviewRuntime:
    """Runtime-Zustand für die Integration der Phase-6D-Prüflisten."""

    original_tabs: object
    original_renderer: object
    fall_tab: object | None = None


def install_fallpruefung_review_integration() -> FallpruefungReviewRuntime:
    """
    Die bisherigen nachrangigen Prüflisten in den Reiter Fall bearbeiten verschieben.

    Die Legacy-App erwartet weiterhin dieselbe Anzahl an Tab-Objekten. Daher bleibt
    der frühere Reiter technisch als unsichtbarer Platzhalter bestehen. Sobald die
    Legacy-App seine Prüflisten rendert, werden sie kontrolliert in den bereits
    vorhandenen Fallprüfungs-Container umgeleitet.
    """
    runtime = FallpruefungReviewRuntime(
        original_tabs=st.tabs,
        original_renderer=review_ui.render_phase6d_review_lists,
    )

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

    st.tabs = patched_tabs
    review_ui.render_phase6d_review_lists = rerouted_review_renderer
    return runtime


def restore_fallpruefung_review_integration(runtime: FallpruefungReviewRuntime) -> None:
    """Streamlit- und Renderer-Patches nach dem Legacy-Lauf vollständig zurücksetzen."""
    review_ui.render_phase6d_review_lists = runtime.original_renderer
    st.tabs = runtime.original_tabs
