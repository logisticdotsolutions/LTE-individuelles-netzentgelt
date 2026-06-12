from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import pandas as pd
import streamlit as st

import manual_override_suggestion_module as suggestion_module
import manual_override_ui_module as override_ui
import phase6d_controller_review_ui as review_ui


FALL_TAB_LABEL = "3. Fall bearbeiten"
REVIEW_TAB_LABEL = "6. Weitere Prüfungen"
HIDDEN_REVIEW_TAB_LABEL = " "
SHORT_GAP_CONTINUITY_MIN_MINUTES = 15
SHORT_GAP_CONTINUITY_MAX_MINUTES = 120
COLD_STAND_PROPOSAL_MIN_MINUTES = 120
COLD_STAND_PROPOSAL_MAX_MINUTES = 480
NO_LTE_ASSIGNMENT_MIN_MINUTES = 480
COLD_STAND_SUGGESTION_TYPE = "POSSIBLE_COLD_STAND_GAP_120_TO_480"
COLD_STAND_SUGGESTION_LABEL = "Kaltabstellung bei GAP über 120 bis 480 Minuten prüfen"
NO_LTE_ASSIGNMENT_SUGGESTION_TYPE = "NO_LTE_ASSIGNMENT_GAP_OVER_480"
NO_LTE_ASSIGNMENT_SUGGESTION_LABEL = "Keine LTE-Zuweisung bei GAP über 480 Minuten prüfen"
NO_LTE_ASSIGNMENT_CLASSIFICATION_CODE = "NO_LTE_ASSIGNMENT"
NO_LTE_ASSIGNMENT_CLASSIFICATION_LABEL = "Keine LTE-Zuweisung"


@dataclass
class FallpruefungReviewRuntime:
    """Runtime-Zustand für Fallprüfungsintegration und Vorschlagslogik."""

    original_tabs: object
    original_renderer: object
    original_cold_stand_suggester: object
    original_gap_continuity_suggester: object
    original_broken_chain_suggester: object
    original_cold_stand_min_minutes: int
    original_cold_stand_label: str | None
    had_original_cold_stand_label: bool
    original_no_lte_assignment_label: str | None
    had_original_no_lte_assignment_label: bool
    original_no_lte_classification_label: str | None
    had_original_no_lte_classification_label: bool
    fall_tab: object | None = None


def _clean(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _bool_flag(value: object) -> bool:
    return _clean(value).lower() in {"true", "1", "yes", "y", "ja"}


def _duration_minutes(period_start_utc: object, period_end_utc: object) -> float | None:
    start = pd.to_datetime(period_start_utc, errors="coerce")
    end = pd.to_datetime(period_end_utc, errors="coerce")
    if pd.isna(start) or pd.isna(end):
        return None
    return float((end - start).total_seconds() / 60.0)


def _gap_duration_minutes(row: pd.Series) -> float | None:
    explicit = pd.to_numeric(row.get("gap_duration_minutes"), errors="coerce")
    if not pd.isna(explicit):
        return float(explicit)
    return _duration_minutes(row.get("period_start_utc"), row.get("period_end_utc"))


def _gap_rows(timeline: pd.DataFrame) -> pd.DataFrame:
    if timeline is None or timeline.empty or "row_type" not in timeline.columns:
        return pd.DataFrame()
    rows = timeline[
        timeline["row_type"].fillna("").astype(str).str.strip().str.upper().eq("GAP")
    ].copy()
    if "gap_relevant_de" in rows.columns:
        rows = rows[rows["gap_relevant_de"].apply(_bool_flag)]
    return rows


def _new_gap_classification(row: pd.Series, *, suggestion_type: str, classification_code: str, reason: str, evidence: str):
    return suggestion_module._new_suggestion(
        suggestion_type=suggestion_type,
        override_type="CLASSIFY_GAP",
        classification_code=classification_code,
        confidence="MEDIUM",
        loco_no=_clean(row.get("loco_no")),
        transport_number=_clean(row.get("transport_number")),
        period_start_utc=(suggestion_module._timestamp_text(row.get("period_start_utc")) or _clean(row.get("period_start_utc"))),
        period_end_utc=(suggestion_module._timestamp_text(row.get("period_end_utc")) or _clean(row.get("period_end_utc"))),
        source_table=_clean(row.get("source_table")),
        source_row_id=_clean(row.get("source_row_id")),
        reason=reason,
        evidence=evidence,
    )


def _build_gap_duration_suggestions(timeline: pd.DataFrame) -> list[object]:
    """Exklusive Dauerklassen für DE-relevante GAP-Zeilen erzeugen."""
    suggestions = []
    for _, row in _gap_rows(timeline).iterrows():
        minutes = _gap_duration_minutes(row)
        if minutes is None or minutes <= COLD_STAND_PROPOSAL_MIN_MINUTES:
            continue
        if minutes <= COLD_STAND_PROPOSAL_MAX_MINUTES:
            suggestions.append(
                _new_gap_classification(
                    row,
                    suggestion_type=COLD_STAND_SUGGESTION_TYPE,
                    classification_code="COLD_STAND",
                    reason="DE-relevante Unterbrechung über 120 bis einschließlich 480 Minuten erkannt. Bitte prüfen, ob eine kalte Abstellung vorliegt.",
                    evidence=f"GAP-Dauer: {minutes:.0f} Minuten; Dauerklasse: > 120 bis <= 480 Minuten.",
                )
            )
        else:
            suggestions.append(
                _new_gap_classification(
                    row,
                    suggestion_type=NO_LTE_ASSIGNMENT_SUGGESTION_TYPE,
                    classification_code=NO_LTE_ASSIGNMENT_CLASSIFICATION_CODE,
                    reason="DE-relevante Unterbrechung über 480 Minuten erkannt. Eine LTE-Zuweisung darf nicht automatisch fortgeschrieben werden. Bitte bestätigen, ob der Zeitraum ohne LTE-Zuweisung bleibt.",
                    evidence=f"GAP-Dauer: {minutes:.0f} Minuten; Dauerklasse: > 480 Minuten.",
                )
            )
    return suggestions


def _filter_short_gap_continuity(candidates: list[object]) -> list[object]:
    """Nachbar-EVU nur für GAPs über 15 bis einschließlich 120 Minuten fortschreiben."""
    result = []
    for candidate in candidates:
        minutes = _duration_minutes(candidate.period_start_utc, candidate.period_end_utc)
        if minutes is not None and SHORT_GAP_CONTINUITY_MIN_MINUTES < minutes <= SHORT_GAP_CONTINUITY_MAX_MINUTES:
            result.append(candidate)
    return result


def _filter_uncertain_broken_chains(candidates: list[object]) -> list[object]:
    """Gebrochene Ortskette nur behalten, wenn keine belastbare Dauerklasse möglich ist."""
    return [
        candidate
        for candidate in candidates
        if _duration_minutes(candidate.period_start_utc, candidate.period_end_utc) is None
    ]


def _filter_legacy_cold_stands(candidates: list[object]) -> list[object]:
    result = []
    for candidate in candidates:
        minutes = _duration_minutes(candidate.period_start_utc, candidate.period_end_utc)
        if minutes is not None and COLD_STAND_PROPOSAL_MIN_MINUTES < minutes <= COLD_STAND_PROPOSAL_MAX_MINUTES:
            result.append(candidate)
    return result


def install_fallpruefung_review_integration() -> FallpruefungReviewRuntime:
    """Prüflisten integrieren und abgestimmte GAP-Dauerklassen aktivieren."""
    runtime = FallpruefungReviewRuntime(
        original_tabs=st.tabs,
        original_renderer=review_ui.render_phase6d_review_lists,
        original_cold_stand_suggester=suggestion_module._suggest_cold_stands,
        original_gap_continuity_suggester=suggestion_module._suggest_gap_performing_ru_from_neighbours,
        original_broken_chain_suggester=suggestion_module._suggest_broken_chain_gaps,
        original_cold_stand_min_minutes=suggestion_module.COLD_STAND_MIN_MINUTES,
        original_cold_stand_label=override_ui.SUGGESTION_TYPE_LABELS.get(COLD_STAND_SUGGESTION_TYPE),
        had_original_cold_stand_label=(COLD_STAND_SUGGESTION_TYPE in override_ui.SUGGESTION_TYPE_LABELS),
        original_no_lte_assignment_label=override_ui.SUGGESTION_TYPE_LABELS.get(NO_LTE_ASSIGNMENT_SUGGESTION_TYPE),
        had_original_no_lte_assignment_label=(NO_LTE_ASSIGNMENT_SUGGESTION_TYPE in override_ui.SUGGESTION_TYPE_LABELS),
        original_no_lte_classification_label=override_ui.CLASSIFICATION_OPTIONS.get(NO_LTE_ASSIGNMENT_CLASSIFICATION_CODE),
        had_original_no_lte_classification_label=(NO_LTE_ASSIGNMENT_CLASSIFICATION_CODE in override_ui.CLASSIFICATION_OPTIONS),
    )

    def cold_stand_suggestions(timeline):
        duration_suggestions = _build_gap_duration_suggestions(timeline)
        if duration_suggestions:
            return duration_suggestions
        return _filter_legacy_cold_stands(runtime.original_cold_stand_suggester(timeline))

    def short_gap_continuity(timeline):
        return _filter_short_gap_continuity(runtime.original_gap_continuity_suggester(timeline))

    def uncertain_broken_chains(timeline):
        return _filter_uncertain_broken_chains(runtime.original_broken_chain_suggester(timeline))

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

    suggestion_module.COLD_STAND_MIN_MINUTES = COLD_STAND_PROPOSAL_MIN_MINUTES
    suggestion_module._suggest_cold_stands = cold_stand_suggestions
    suggestion_module._suggest_gap_performing_ru_from_neighbours = short_gap_continuity
    suggestion_module._suggest_broken_chain_gaps = uncertain_broken_chains
    override_ui.SUGGESTION_TYPE_LABELS[COLD_STAND_SUGGESTION_TYPE] = COLD_STAND_SUGGESTION_LABEL
    override_ui.SUGGESTION_TYPE_LABELS[NO_LTE_ASSIGNMENT_SUGGESTION_TYPE] = NO_LTE_ASSIGNMENT_SUGGESTION_LABEL
    override_ui.CLASSIFICATION_OPTIONS[NO_LTE_ASSIGNMENT_CLASSIFICATION_CODE] = NO_LTE_ASSIGNMENT_CLASSIFICATION_LABEL
    st.tabs = patched_tabs
    review_ui.render_phase6d_review_lists = rerouted_review_renderer
    return runtime


def restore_fallpruefung_review_integration(runtime: FallpruefungReviewRuntime) -> None:
    """Streamlit-, Renderer- und Vorschlags-Patches vollständig zurücksetzen."""
    review_ui.render_phase6d_review_lists = runtime.original_renderer
    suggestion_module._suggest_cold_stands = runtime.original_cold_stand_suggester
    suggestion_module._suggest_gap_performing_ru_from_neighbours = runtime.original_gap_continuity_suggester
    suggestion_module._suggest_broken_chain_gaps = runtime.original_broken_chain_suggester
    suggestion_module.COLD_STAND_MIN_MINUTES = runtime.original_cold_stand_min_minutes
    if runtime.had_original_cold_stand_label:
        override_ui.SUGGESTION_TYPE_LABELS[COLD_STAND_SUGGESTION_TYPE] = runtime.original_cold_stand_label or ""
    else:
        override_ui.SUGGESTION_TYPE_LABELS.pop(COLD_STAND_SUGGESTION_TYPE, None)
    if runtime.had_original_no_lte_assignment_label:
        override_ui.SUGGESTION_TYPE_LABELS[NO_LTE_ASSIGNMENT_SUGGESTION_TYPE] = runtime.original_no_lte_assignment_label or ""
    else:
        override_ui.SUGGESTION_TYPE_LABELS.pop(NO_LTE_ASSIGNMENT_SUGGESTION_TYPE, None)
    if runtime.had_original_no_lte_classification_label:
        override_ui.CLASSIFICATION_OPTIONS[NO_LTE_ASSIGNMENT_CLASSIFICATION_CODE] = runtime.original_no_lte_classification_label or ""
    else:
        override_ui.CLASSIFICATION_OPTIONS.pop(NO_LTE_ASSIGNMENT_CLASSIFICATION_CODE, None)
    st.tabs = runtime.original_tabs
