from __future__ import annotations

from typing import Callable

import loco_timeline_calendar_runtime_module as timeline
from broken_route_chain_policy_module import is_no_lte_assignment_marker

NO_LTE_ASSIGNMENT_UI_MARKER = "NETZENTGELT_NO_LTE_ASSIGNMENT_GREY_TIMELINE_V1_20260630"


def install_no_lte_assignment_policy_runtime() -> Callable | None:
    """Render Keine LTE Zuordnung/Zuweisung as grey Outside-DE context, not as GAP/error."""
    original_classifier = timeline.classify_timeline_status
    if getattr(original_classifier, "_no_lte_assignment_policy_installed", False):
        return original_classifier

    def classify_without_no_lte_as_problem(
        *,
        row_type: str,
        is_de_relevant: bool,
        holder: str = "",
        performing_ru: str = "",
        rules: str = "",
        message: str = "",
        decision_reason: str = "",
    ) -> str:
        if is_no_lte_assignment_marker(
            row_type,
            holder,
            performing_ru,
            rules,
            message,
            decision_reason,
        ):
            return "Außerhalb DE"
        return original_classifier(
            row_type=row_type,
            is_de_relevant=is_de_relevant,
            holder=holder,
            performing_ru=performing_ru,
            rules=rules,
            message=message,
            decision_reason=decision_reason,
        )

    classify_without_no_lte_as_problem._no_lte_assignment_policy_installed = True
    classify_without_no_lte_as_problem._no_lte_assignment_policy_original = original_classifier
    timeline.classify_timeline_status = classify_without_no_lte_as_problem
    return original_classifier


def restore_no_lte_assignment_policy_runtime(original_classifier: Callable | None) -> None:
    if original_classifier is None:
        return
    timeline.classify_timeline_status = original_classifier
