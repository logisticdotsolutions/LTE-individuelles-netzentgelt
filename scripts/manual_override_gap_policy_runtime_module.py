from __future__ import annotations


GAP_POLICY_UI_LABEL_MARKER = "NETZENTGELT_GAP_POLICY_UI_LABELS_20260618"


def install_gap_policy_labels() -> None:
    """Register operator-friendly labels and remove UKL quarter-hour UI proposals."""
    import manual_override_suggestion_module as suggestion_module
    import manual_override_ui_module as override_ui

    override_ui.CLASSIFICATION_OPTIONS.setdefault(
        "NO_LTE_ASSIGNMENT",
        "Keine LTE-Zuweisung / nicht im Report",
    )
    override_ui.SUGGESTION_TYPE_LABELS.update(
        {
            "GAP_NO_LTE_ASSIGNMENT": "Keine LTE-Zuweisung / nicht im Report",
            "GAP_PERFORMING_RU_FROM_BOTH_NEIGHBOURS": "EVU aus direkter GAP-Umgebung übernehmen",
            "POSSIBLE_COLD_STAND_SAME_LOCATION": "Kaltabstellung ab GAP über 120 Minuten prüfen",
        }
    )

    if getattr(suggestion_module, "_PHASE11I_NO_QUARTER_HOUR_UI_PATCHED", False):
        return

    original_build_suggestion_table = suggestion_module.build_suggestion_table

    def build_suggestion_table_without_quarter_hour(*args, **kwargs):
        result = original_build_suggestion_table(*args, **kwargs)
        if result is None or result.empty or "suggestion_type" not in result.columns:
            return result
        return result[
            result["suggestion_type"].fillna("").astype(str).ne("BORDER_QUARTER_HOUR_REVIEW")
        ].reset_index(drop=True)

    suggestion_module.build_suggestion_table = build_suggestion_table_without_quarter_hour
    suggestion_module._PHASE11I_NO_QUARTER_HOUR_UI_PATCHED = True
