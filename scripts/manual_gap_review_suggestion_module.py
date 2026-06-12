from __future__ import annotations

import pandas as pd

import manual_override_suggestion_module as suggestion_module
from manual_gap_ui_labels import GAP_REVIEW_MIN_MINUTES, clean, duration_minutes


GAP_REVIEW_SUGGESTION_TYPE = "GAP_OVER_120_MANUAL_CLASSIFICATION"
GAP_REVIEW_SUGGESTION_LABEL = "GAP über 120 Minuten fachlich bewerten"
_LEGACY_COLD_STAND_SUGGESTER = suggestion_module._suggest_cold_stands


def _bool_flag(value: object) -> bool:
    return clean(value).lower() in {"true", "1", "yes", "y", "ja"}


def _row_duration_minutes(row: pd.Series) -> int | None:
    explicit = pd.to_numeric(row.get("gap_duration_minutes"), errors="coerce")
    if not pd.isna(explicit):
        return max(0, int(round(float(explicit))))
    return duration_minutes(row.get("period_start_utc"), row.get("period_end_utc"))


def build_gap_review_suggestions(timeline: pd.DataFrame) -> list[object]:
    """Create manual-review proposals without deciding the fachliche GAP reason."""
    if timeline is None or timeline.empty or "row_type" not in timeline.columns:
        return []
    rows = timeline[
        timeline["row_type"].fillna("").astype(str).str.strip().str.upper().eq("GAP")
    ].copy()
    if rows.empty:
        return _LEGACY_COLD_STAND_SUGGESTER(timeline)
    if "gap_relevant_de" in rows.columns:
        rows = rows[rows["gap_relevant_de"].apply(_bool_flag)]
    suggestions = []
    for _, row in rows.iterrows():
        minutes = _row_duration_minutes(row)
        if minutes is None or minutes <= GAP_REVIEW_MIN_MINUTES:
            continue
        suggestions.append(
            suggestion_module._new_suggestion(
                suggestion_type=GAP_REVIEW_SUGGESTION_TYPE,
                override_type="CLASSIFY_GAP",
                classification_code="",
                confidence="LOW",
                loco_no=clean(row.get("loco_no")),
                transport_number=clean(row.get("transport_number")),
                period_start_utc=(
                    suggestion_module._timestamp_text(row.get("period_start_utc"))
                    or clean(row.get("period_start_utc"))
                ),
                period_end_utc=(
                    suggestion_module._timestamp_text(row.get("period_end_utc"))
                    or clean(row.get("period_end_utc"))
                ),
                source_table=clean(row.get("source_table")),
                source_row_id=clean(row.get("source_row_id")),
                reason=(
                    "GAP über 120 Minuten: bitte fachlich entscheiden, ob eine Kaltabstellung, "
                    "eine Übergabe an ein anderes EVU ohne LTE-Zuweisung oder ein anderer Grund vorliegt."
                ),
                evidence=f"GAP-Dauer: {minutes} Minuten.",
            )
        )
    return suggestions
