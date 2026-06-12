from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import streamlit as st

import manual_override_suggestion_module as suggestion_module
import manual_override_ui_module as override_ui
import phase6d_controller_review_ui as review_ui
from manual_gap_case_ui_module import decorate_case_table, decorate_context_table
from manual_gap_review_suggestion_module import (
    GAP_REVIEW_SUGGESTION_LABEL,
    GAP_REVIEW_SUGGESTION_TYPE,
    build_gap_review_suggestions,
)
from manual_gap_ui_labels import NO_LTE_ASSIGNMENT_CODE, NO_LTE_ASSIGNMENT_LABEL


FALL_TAB_LABEL = "3. Fall bearbeiten"
REVIEW_TAB_LABEL = "6. Weitere Prüfungen"
HIDDEN_REVIEW_TAB_LABEL = " "
GAP_REVIEW_MIN_MINUTES = 120


@dataclass
class FallpruefungReviewRuntime:
    """Runtime-Zustand für Fallprüfungsintegration und Vorschlagslogik."""

    original_tabs: object
    original_renderer: object
    original_case_table_builder: object
    original_context_table_builder: object | None
    had_original_context_table_builder: bool
    original_cold_stand_suggester: object
    original_cold_stand_min_minutes: int
    original_gap_review_label: str | None
    had_original_gap_review_label: bool
    original_no_lte_label: str | None
    had_original_no_lte_label: bool
    fall_tab: object | None = None


def install_fallpruefung_review_integration() -> FallpruefungReviewRuntime:
    """Prüflisten, verständliche Dropdowns und GAP-Einzelfallprüfung aktivieren."""
    had_context_table = hasattr(override_ui, "_context_table")
    runtime = FallpruefungReviewRuntime(
        original_tabs=st.tabs,
        original_renderer=review_ui.render_phase6d_review_lists,
        original_case_table_builder=override_ui._build_case_table,
        original_context_table_builder=getattr(override_ui, "_context_table", None),
        had_original_context_table_builder=had_context_table,
        original_cold_stand_suggester=suggestion_module._suggest_cold_stands,
        original_cold_stand_min_minutes=suggestion_module.COLD_STAND_MIN_MINUTES,
        original_gap_review_label=override_ui.SUGGESTION_TYPE_LABELS.get(GAP_REVIEW_SUGGESTION_TYPE),
        had_original_gap_review_label=(GAP_REVIEW_SUGGESTION_TYPE in override_ui.SUGGESTION_TYPE_LABELS),
        original_no_lte_label=override_ui.CLASSIFICATION_OPTIONS.get(NO_LTE_ASSIGNMENT_CODE),
        had_original_no_lte_label=(NO_LTE_ASSIGNMENT_CODE in override_ui.CLASSIFICATION_OPTIONS),
    )

    def case_table_builder(findings, timeline):
        return decorate_case_table(runtime.original_case_table_builder(findings, timeline))

    def context_table_builder(case, override_type):
        if not callable(runtime.original_context_table_builder):
            return None
        original = runtime.original_context_table_builder(case, override_type)
        return decorate_context_table(original, case)

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

    suggestion_module.COLD_STAND_MIN_MINUTES = GAP_REVIEW_MIN_MINUTES
    suggestion_module._suggest_cold_stands = build_gap_review_suggestions
    override_ui._build_case_table = case_table_builder
    if callable(runtime.original_context_table_builder):
        override_ui._context_table = context_table_builder
    override_ui.SUGGESTION_TYPE_LABELS[GAP_REVIEW_SUGGESTION_TYPE] = GAP_REVIEW_SUGGESTION_LABEL
    override_ui.CLASSIFICATION_OPTIONS[NO_LTE_ASSIGNMENT_CODE] = NO_LTE_ASSIGNMENT_LABEL
    st.tabs = patched_tabs
    review_ui.render_phase6d_review_lists = rerouted_review_renderer
    return runtime


def restore_fallpruefung_review_integration(runtime: FallpruefungReviewRuntime) -> None:
    """Streamlit-, Renderer- und Vorschlags-Patches vollständig zurücksetzen."""
    review_ui.render_phase6d_review_lists = runtime.original_renderer
    override_ui._build_case_table = runtime.original_case_table_builder
    if runtime.had_original_context_table_builder:
        override_ui._context_table = runtime.original_context_table_builder
    else:
        override_ui.__dict__.pop("_context_table", None)
    suggestion_module._suggest_cold_stands = runtime.original_cold_stand_suggester
    suggestion_module.COLD_STAND_MIN_MINUTES = runtime.original_cold_stand_min_minutes

    if runtime.had_original_gap_review_label:
        override_ui.SUGGESTION_TYPE_LABELS[GAP_REVIEW_SUGGESTION_TYPE] = runtime.original_gap_review_label or ""
    else:
        override_ui.SUGGESTION_TYPE_LABELS.pop(GAP_REVIEW_SUGGESTION_TYPE, None)

    if runtime.had_original_no_lte_label:
        override_ui.CLASSIFICATION_OPTIONS[NO_LTE_ASSIGNMENT_CODE] = runtime.original_no_lte_label or ""
    else:
        override_ui.CLASSIFICATION_OPTIONS.pop(NO_LTE_ASSIGNMENT_CODE, None)

    st.tabs = runtime.original_tabs
