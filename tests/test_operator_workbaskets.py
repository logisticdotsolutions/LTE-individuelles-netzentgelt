from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from operator_gate_detail_runtime_module import (  # noqa: E402
    build_business_workbaskets,
    install_operator_gate_detail_runtime,
)


def test_business_workbaskets_have_only_two_business_baskets() -> None:
    baskets = build_business_workbaskets(
        export_gate=pd.DataFrame(),
        global_export_blockers=pd.DataFrame(),
        findings=pd.DataFrame(),
    )

    assert list(baskets.keys()) == [
        "Fehler in Lokbewegung",
        "Fehlende Loknummer / Dummylok",
    ]


def test_business_workbaskets_exclude_warning_and_info_side_lists() -> None:
    export_gate = pd.DataFrame(
        [
            {
                "gate_status": "WARNING",
                "loco_no": "L1",
                "coverage_date": "2026-06-18",
                "performing_ru": "LTE DE",
                "coverage_pct": 100,
                "unresolved_gap_minutes": 30,
                "overlap_minutes": 0,
                "gate_reason": "INFO-Findings=1",
            },
        ]
    )
    findings = pd.DataFrame(
        [
            {
                "severity": "INFO",
                "rule_id": "R010.5",
                "loco_no": "L1",
                "transport_number": "T1",
                "performing_ru": "LTE DE",
                "period_start_utc": "2026-06-18T08:00:00",
                "period_end_utc": "2026-06-18T09:00:00",
                "message": "Hinweis",
            },
        ]
    )

    baskets = build_business_workbaskets(export_gate, pd.DataFrame(), findings)

    assert baskets["Fehler in Lokbewegung"].empty
    assert baskets["Fehlende Loknummer / Dummylok"].empty


def test_blocked_gate_row_goes_to_movement_error_once_even_with_matching_finding() -> None:
    export_gate = pd.DataFrame(
        [
            {
                "gate_status": "BLOCKED",
                "loco_no": "L2",
                "coverage_date": "2026-06-18",
                "performing_ru": "LTE NL",
                "coverage_pct": 100,
                "unresolved_gap_minutes": 0,
                "overlap_minutes": 30,
                "gate_reason": "Overlap-Minuten=30",
            },
        ]
    )
    findings = pd.DataFrame(
        [
            {
                "severity": "ERROR",
                "rule_id": "R011",
                "loco_no": "L2",
                "transport_number": "T2",
                "performing_ru": "LTE NL",
                "period_start_utc": "2026-06-18T08:30:00",
                "period_end_utc": "2026-06-18T09:00:00",
                "message": "Overlap",
            },
        ]
    )

    install_operator_gate_detail_runtime()
    baskets = build_business_workbaskets(export_gate, pd.DataFrame(), findings)

    movement_errors = baskets["Fehler in Lokbewegung"]
    assert len(movement_errors) == 1
    assert movement_errors.iloc[0]["Loknummer"] == "L2"
    assert "Zeitliche Ueberschneidung" in movement_errors.iloc[0]["Warum?"]


def test_r012_global_blocker_goes_to_missing_loco_basket() -> None:
    global_blockers = pd.DataFrame(
        [
            {
                "blocker_date": "2026-06-18",
                "rule_id": "R012",
                "transport_number": "T3",
                "performing_ru": "LTE DE",
                "message": "Dummy locomotive / Loknummer fehlt",
            },
            {
                "blocker_date": "2026-06-18",
                "rule_id": "R009",
                "transport_number": "T4",
                "performing_ru": "",
                "message": "PerformingRU fehlt",
            },
        ]
    )

    baskets = build_business_workbaskets(pd.DataFrame(), global_blockers, pd.DataFrame())

    missing = baskets["Fehlende Loknummer / Dummylok"]
    assert len(missing) == 1
    assert missing.iloc[0]["Transportnummer"] == "T3"
    assert missing.iloc[0]["Problem"] == "Dummy-Lok"


def test_dummy_gate_row_is_not_duplicated_in_movement_basket() -> None:
    export_gate = pd.DataFrame(
        [
            {
                "gate_status": "BLOCKED",
                "loco_no": "Dummy-Lok",
                "coverage_date": "2026-06-18",
                "performing_ru": "LTE DE",
                "coverage_pct": 100,
                "unresolved_gap_minutes": 0,
                "overlap_minutes": 0,
                "gate_reason": "Dummy Lok",
            },
        ]
    )
    findings = pd.DataFrame(
        [
            {
                "severity": "ERROR",
                "rule_id": "R012",
                "loco_no": "Dummy-Lok",
                "transport_number": "T5",
                "performing_ru": "LTE DE",
                "period_start_utc": "2026-06-18T08:00:00",
                "period_end_utc": "2026-06-18T09:00:00",
                "message": "Dummy Lok",
                "row_type": "RAW_DUMMY_LOCOMOTIVE",
            },
        ]
    )

    install_operator_gate_detail_runtime()
    baskets = build_business_workbaskets(export_gate, pd.DataFrame(), findings)

    assert baskets["Fehler in Lokbewegung"].empty
