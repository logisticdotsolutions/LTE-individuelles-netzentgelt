from __future__ import annotations


GAP_POLICY_UI_LABEL_MARKER = "NETZENTGELT_GAP_POLICY_UI_LABELS_20260618"


def install_gap_policy_labels() -> None:
    """Register operator-friendly labels for the mutually exclusive GAP policy."""
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
