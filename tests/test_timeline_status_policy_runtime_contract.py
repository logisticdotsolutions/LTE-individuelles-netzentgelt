from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import loco_timeline_calendar_runtime_module as timeline  # noqa: E402
from no_lte_assignment_policy_runtime_module import (  # noqa: E402
    decide_timeline_status,
    install_no_lte_assignment_policy_runtime,
    restore_no_lte_assignment_policy_runtime,
)


def test_not_in_report_status_is_outside_not_assigned():
    status, reason = decide_timeline_status(
        row_type="MOVEMENT",
        is_de_relevant=True,
        holder="ELL Austria GmbH",
        performing_ru="LTE NL - LTE Netherlands B.V.",
        report_scope="NOT_IN_REPORT",
        route_type="Inland",
        event_type="In DE",
    )

    assert status == "Außerhalb DE"
    assert "NOT_IN_REPORT" in reason


def test_normal_gap_stays_gap():
    status, reason = decide_timeline_status(
        row_type="GAP",
        is_de_relevant=True,
        holder="LTE Holding",
        performing_ru="LTE DE",
        report_scope="IN_REPORT",
        route_type="Inland",
        event_type="In DE",
        gap_relevant_de=True,
    )

    assert status == "GAP"
    assert "Lücke" in reason


def test_explicit_no_lte_assignment_stays_outside():
    marker = "Keine LTE Zuordnung"
    status, reason = decide_timeline_status(
        row_type="GAP",
        is_de_relevant=True,
        holder=marker,
        performing_ru=marker,
        report_scope="IN_REPORT",
        route_type="Inland",
        event_type="In DE",
        gap_relevant_de=True,
    )

    assert status == "Außerhalb DE"
    assert "Keine-LTE" in reason


def test_valid_de_assignment_stays_assigned():
    status, reason = decide_timeline_status(
        row_type="MOVEMENT",
        is_de_relevant=True,
        holder="ELL Austria GmbH",
        performing_ru="LTE NL - LTE Netherlands B.V.",
        report_scope="IN_REPORT",
        route_type="Inland",
        event_type="In DE",
    )

    assert status == "Zugewiesen"
    assert "Zuordnung vorhanden" in reason


def test_installed_classifier_never_returns_green_for_not_in_report_row_type():
    original = install_no_lte_assignment_policy_runtime()
    try:
        status = timeline.classify_timeline_status(
            row_type="NOT_IN_REPORT",
            is_de_relevant=True,
            holder="ELL Austria GmbH",
            performing_ru="LTE NL - LTE Netherlands B.V.",
        )
    finally:
        restore_no_lte_assignment_policy_runtime(original)

    assert status == "Außerhalb DE"
