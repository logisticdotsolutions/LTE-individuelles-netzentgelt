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
COLD_STAND_PROPOSAL_MIN_MINUTES = 120
COLD_STAND_SUGGESTION_TYPE = "POSSIBLE_COLD_STAND_GAP_OVER_120"
COLD_STAND_SUGGESTION_LABEL = "Kaltabstellung ab GAP über 120 Minuten prüfen"


@dataclass
class FallpruefungReviewRuntime:
    """Runtime-Zustand für Fallprüfungsintegration und Vorschlagslogik."""

    original_tabs: object
    original_renderer: object
    original_cold_stand_suggester: object
    original_cold_stand_min_minutes: int
    original_cold_stand_label: str | None
    had_original_cold_stand_label: bool
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


def _new_cold_stand_suggestion(
    *,
    loco_no: object,
    transport_number: object,
    period_start_utc: object,
    period_end_utc: object,
    source_table: object,
    source_row_id: object,
    minutes: float,
    evidence_prefix: str,
) -> object:
    return suggestion_module._new_suggestion(
        suggestion_type=COLD_STAND_SUGGESTION_TYPE,
        override_type="CLASSIFY_GAP",
        classification_code="COLD_STAND",
        confidence="MEDIUM",
        suggested_value="Mögliche kalte Abstellung",
        loco_no=_clean(loco_no),
        transport_number=_clean(transport_number),
        period_start_utc=(
            suggestion_module._timestamp_text(period_start_utc)
            or _clean(period_start_utc)
        ),
        period_end_utc=(
            suggestion_module._timestamp_text(period_end_utc)
            or _clean(period_end_utc)
        ),
        source_table=_clean(source_table),
        source_row_id=_clean(source_row_id),
        reason=(
            "DE-relevante Unterbrechung über 120 Minuten erkannt. "
            "Bitte prüfen, ob eine kalte Abstellung vorliegt."
        ),
        evidence=(
            f"{evidence_prefix} GAP-Dauer: {minutes:.0f} Minuten; "
            f"Schwellwert: > {COLD_STAND_PROPOSAL_MIN_MINUTES} Minuten."
        ),
    )


def _build_gap_cold_stand_suggestions(timeline: pd.DataFrame) -> list[object]:
    """Für jede DE-relevante GAP > 120 Minuten einen manuellen Prüf-Vorschlag erzeugen."""
    if timeline is None or timeline.empty or "row_type" not in timeline.columns:
        return []

    gap_rows = timeline[
        timeline["row_type"].fillna("").astype(str).str.strip().str.upper().eq("GAP")
    ].copy()

    if gap_rows.empty:
        return []

    if "gap_relevant_de" in gap_rows.columns:
        gap_rows = gap_rows[gap_rows["gap_relevant_de"].apply(_bool_flag)]

    suggestions = []
    for _, row in gap_rows.iterrows():
        minutes = _gap_duration_minutes(row)
        if minutes is None or minutes <= COLD_STAND_PROPOSAL_MIN_MINUTES:
            continue
        suggestions.append(
            _new_cold_stand_suggestion(
                loco_no=row.get("loco_no"),
                transport_number=row.get("transport_number"),
                period_start_utc=row.get("period_start_utc"),
                period_end_utc=row.get("period_end_utc"),
                source_table=row.get("source_table"),
                source_row_id=row.get("source_row_id"),
                minutes=minutes,
                evidence_prefix="Explizite GAP-Zeile.",
            )
        )
    return suggestions


def _build_legacy_movement_cold_stand_suggestions(timeline: pd.DataFrame) -> list[object]:
    """Fallback für ältere Timeline-Stände ohne explizite GAP-Zeilen."""
    if timeline is None or timeline.empty or "row_type" not in timeline.columns:
        return []

    movements = timeline[
        timeline["row_type"].fillna("").astype(str).str.strip().str.upper().eq("MOVEMENT")
    ].copy()
    if movements.empty:
        return []

    movements["_cold_stand_sort_ts"] = pd.to_datetime(
        movements.get("sequence_ts", movements.get("period_start_utc", "")),
        errors="coerce",
    )
    suggestions = []
    for loco_no, group in movements.groupby("loco_no", dropna=False):
        ordered = group.sort_values(["_cold_stand_sort_ts", "source_row_id"], na_position="last").reset_index(drop=True)
        for index in range(len(ordered) - 1):
            previous = ordered.iloc[index]
            following = ordered.iloc[index + 1]
            previous_end = pd.to_datetime(previous.get("period_end_utc"), errors="coerce")
            following_start = pd.to_datetime(following.get("period_start_utc"), errors="coerce")
            if pd.isna(previous_end) or pd.isna(following_start) or following_start <= previous_end:
                continue
            minutes = float((following_start - previous_end).total_seconds() / 60.0)
            if minutes <= COLD_STAND_PROPOSAL_MIN_MINUTES:
                continue
            previous_scope = _clean(previous.get("report_scope")).upper()
            following_scope = _clean(following.get("report_scope")).upper()
            if previous_scope and following_scope and "IN_REPORT" not in {previous_scope, following_scope}:
                continue
            previous_location = _clean(previous.get("destination_name"))
            following_location = _clean(following.get("origin_name"))
            if previous_location and following_location and previous_location != following_location:
                continue
            suggestions.append(
                _new_cold_stand_suggestion(
                    loco_no=loco_no,
                    transport_number=previous.get("transport_number"),
                    period_start_utc=previous_end,
                    period_end_utc=following_start,
                    source_table=previous.get("source_table"),
                    source_row_id=previous.get("source_row_id"),
                    minutes=minutes,
                    evidence_prefix="Legacy-Timeline ohne explizite GAP-Zeile.",
                )
            )
    return suggestions


def _filter_legacy_cold_stand_suggestions(candidates: list[object]) -> list[object]:
    """Legacy-Nachbarlogik nur für ältere Timeline-Stände ohne GAP-Zeilen erhalten."""
    result = []
    for candidate in candidates:
        minutes = _duration_minutes(candidate.period_start_utc, candidate.period_end_utc)
        if minutes is not None and minutes > COLD_STAND_PROPOSAL_MIN_MINUTES:
            result.append(candidate)
    return result


def install_fallpruefung_review_integration() -> FallpruefungReviewRuntime:
    """Prüflisten integrieren und Kaltabstellungsvorschläge für GAP > 120 Minuten aktivieren."""
    runtime = FallpruefungReviewRuntime(
        original_tabs=st.tabs,
        original_renderer=review_ui.render_phase6d_review_lists,
        original_cold_stand_suggester=suggestion_module._suggest_cold_stands,
        original_cold_stand_min_minutes=suggestion_module.COLD_STAND_MIN_MINUTES,
        original_cold_stand_label=override_ui.SUGGESTION_TYPE_LABELS.get(COLD_STAND_SUGGESTION_TYPE),
        had_original_cold_stand_label=(COLD_STAND_SUGGESTION_TYPE in override_ui.SUGGESTION_TYPE_LABELS),
    )

    def cold_stand_suggestions(timeline):
        gap_suggestions = _build_gap_cold_stand_suggestions(timeline)
        if gap_suggestions:
            return gap_suggestions
        movement_suggestions = _build_legacy_movement_cold_stand_suggestions(timeline)
        if movement_suggestions:
            return movement_suggestions
        return _filter_legacy_cold_stand_suggestions(
            runtime.original_cold_stand_suggester(timeline)
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
    override_ui.SUGGESTION_TYPE_LABELS[COLD_STAND_SUGGESTION_TYPE] = COLD_STAND_SUGGESTION_LABEL
    st.tabs = patched_tabs
    review_ui.render_phase6d_review_lists = rerouted_review_renderer
    return runtime


def restore_fallpruefung_review_integration(runtime: FallpruefungReviewRuntime) -> None:
    """Streamlit-, Renderer- und Vorschlags-Patches vollständig zurücksetzen."""
    review_ui.render_phase6d_review_lists = runtime.original_renderer
    suggestion_module._suggest_cold_stands = runtime.original_cold_stand_suggester
    suggestion_module.COLD_STAND_MIN_MINUTES = runtime.original_cold_stand_min_minutes

    if runtime.had_original_cold_stand_label:
        override_ui.SUGGESTION_TYPE_LABELS[COLD_STAND_SUGGESTION_TYPE] = runtime.original_cold_stand_label or ""
    else:
        override_ui.SUGGESTION_TYPE_LABELS.pop(COLD_STAND_SUGGESTION_TYPE, None)

    st.tabs = runtime.original_tabs
