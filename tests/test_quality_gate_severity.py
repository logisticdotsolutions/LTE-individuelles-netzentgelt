from __future__ import annotations

"""Severity-Blocking-Tests für quality_gate_module.

Prüft, dass das Export-Gate korrekt auf unterschiedliche Finding-Schweregrade reagiert:
- MANUAL_REVIEW → BLOCKED (bisher nicht explizit getestet)
- INFO          → WARNING  (nicht blockierend)
- Keine Findings → READY

Diese Tests schließen eine Lücke im bestehenden test_phase6d_quality_gate.py,
das nur ERROR/Overlap-Pfade und R016 abdeckt.
"""

from datetime import datetime

import pytest

import quality_gate_module
import rule_engine_hardening_phase6c as phase6c
from tests.support.builders import (
    create_core_timeline,
    create_dq_metadata,
    create_findings_shell,
    ensure_phase6c_columns,
    insert_row,
    movement,
)


def _gate_status(con) -> str:
    return con.execute(
        "select gate_status from dq_export_gate limit 1"
    ).fetchone()[0]


def _prepare_base(con, rows):
    """Timeline und Metadaten aufbauen, Findings-Tabelle bereitstellen."""
    create_core_timeline(con)
    ensure_phase6c_columns(con)
    for row in rows:
        insert_row(con, "core_loco_timeline", row)
    con.execute("update core_loco_timeline set export_blocking=false where row_type='MOVEMENT'")
    create_findings_shell(con)
    create_dq_metadata(con)
    phase6c.build_central_de_usage_segments(con, "RUN_TEST")


def _insert_finding(con, severity: str, loco_no: str = "91800000001-1") -> None:
    """Synthetischen DQ-Befund einfügen (vor build_quality_gate_tables aufrufen)."""
    period = datetime(2026, 6, 1, 10, 0)
    con.execute(
        """
        insert into dq_findings (
            run_id, severity, rule_id, rule_group,
            loco_no, transport_number, performing_ru, row_type,
            movement_sequence_no, period_start_utc, period_end_utc,
            message, suggested_action, status, source_table, source_row_id
        ) values (
            'RUN_TEST', ?, 'TEST-RULE', 'TEST',
            ?, 'TR-1', 'RU GmbH', 'MOVEMENT',
            1, ?, ?,
            'Testbefund', 'Keine Aktion', 'open', 'test', 1
        )
        """,
        [severity, loco_no, period, period],
    )


@pytest.mark.integration
def test_manual_review_finding_blocks_export_gate(con) -> None:
    """MANUAL_REVIEW-Befunde müssen das Export-Gate auf BLOCKED setzen.

    BLOCKING_SEVERITIES enthält MANUAL_REVIEW (quality_gate_module.py:34).
    Dieser Test stellt sicher, dass die Gate-Status-Ableitung korrekt reagiert.
    """
    rows = [movement(1, period_start_utc=datetime(2026, 6, 1, 10), period_end_utc=datetime(2026, 6, 1, 11), actual_departure_ts=datetime(2026, 6, 1, 10), actual_arrival_ts=datetime(2026, 6, 1, 11), sequence_ts=datetime(2026, 6, 1, 10))]
    _prepare_base(con, rows)
    _insert_finding(con, "MANUAL_REVIEW")
    quality_gate_module.build_quality_gate_tables(con, "RUN_TEST")

    assert _gate_status(con) == "BLOCKED", (
        "MANUAL_REVIEW-Befund muss gate_status=BLOCKED erzeugen"
    )
    manual_count = con.execute(
        "select manual_review_findings from dq_export_gate limit 1"
    ).fetchone()[0]
    assert manual_count >= 1


@pytest.mark.integration
def test_info_finding_produces_warning_not_blocked(con) -> None:
    """INFO-Befunde dürfen das Export-Gate nicht auf BLOCKED setzen (nur WARNING).

    INFO-Findings blockieren nicht den Export – das ist fachlich gewollt.
    """
    rows = [movement(1, period_start_utc=datetime(2026, 6, 1, 10), period_end_utc=datetime(2026, 6, 1, 11), actual_departure_ts=datetime(2026, 6, 1, 10), actual_arrival_ts=datetime(2026, 6, 1, 11), sequence_ts=datetime(2026, 6, 1, 10))]
    _prepare_base(con, rows)
    _insert_finding(con, "INFO")
    quality_gate_module.build_quality_gate_tables(con, "RUN_TEST")

    status = _gate_status(con)
    assert status in ("WARNING", "READY"), (
        f"INFO-Befund darf nicht BLOCKED erzeugen, war: {status}"
    )
    assert status != "BLOCKED"


@pytest.mark.integration
def test_no_findings_produces_ready_gate(con) -> None:
    """Ohne DQ-Befunde und ohne GAPs muss das Export-Gate READY sein."""
    rows = [movement(1, period_start_utc=datetime(2026, 6, 1, 10), period_end_utc=datetime(2026, 6, 1, 11), actual_departure_ts=datetime(2026, 6, 1, 10), actual_arrival_ts=datetime(2026, 6, 1, 11), sequence_ts=datetime(2026, 6, 1, 10))]
    _prepare_base(con, rows)
    quality_gate_module.build_quality_gate_tables(con, "RUN_TEST")

    assert _gate_status(con) == "READY", (
        "Ohne Befunde und ohne GAPs muss gate_status=READY sein"
    )


@pytest.mark.unit
def test_blocking_severities_constant() -> None:
    """BLOCKING_SEVERITIES muss ERROR und MANUAL_REVIEW enthalten."""
    assert "ERROR" in quality_gate_module.BLOCKING_SEVERITIES
    assert "MANUAL_REVIEW" in quality_gate_module.BLOCKING_SEVERITIES
    assert "INFO" not in quality_gate_module.BLOCKING_SEVERITIES
