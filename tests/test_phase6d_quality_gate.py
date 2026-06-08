from __future__ import annotations

from datetime import datetime

import pytest

import quality_gate_module
import rule_engine_hardening_phase6c as phase6c
import rule_engine_hardening_phase6d as phase6d
from tests.support.builders import (
    create_core_timeline,
    create_dq_metadata,
    create_findings_shell,
    create_rule_catalog_shell,
    ensure_phase6c_columns,
    insert_row,
    movement,
)


def prepare_gate(con, rows):
    create_core_timeline(con)
    ensure_phase6c_columns(con)
    for row in rows:
        insert_row(con, "core_loco_timeline", row)
    con.execute("update core_loco_timeline set export_blocking=false where row_type='MOVEMENT'")
    create_findings_shell(con)
    create_dq_metadata(con)
    phase6c.build_central_de_usage_segments(con, "RUN_TEST")
    quality_gate_module.build_quality_gate_tables(con, "RUN_TEST")


@pytest.mark.integration
def test_quality_gate_counts_true_overlap_and_phase6d_exact_minutes(con):
    rows = [
        movement(1, transport_number="TR-A", period_start_utc=datetime(2026, 6, 1, 10), period_end_utc=datetime(2026, 6, 1, 12), actual_departure_ts=datetime(2026, 6, 1, 10), actual_arrival_ts=datetime(2026, 6, 1, 12), sequence_ts=datetime(2026, 6, 1, 10)),
        movement(2, transport_number="TR-B", period_start_utc=datetime(2026, 6, 1, 11, 30), period_end_utc=datetime(2026, 6, 1, 13), actual_departure_ts=datetime(2026, 6, 1, 11, 30), actual_arrival_ts=datetime(2026, 6, 1, 13), sequence_ts=datetime(2026, 6, 1, 11, 30)),
    ]
    prepare_gate(con, rows)
    assert con.execute("select overlap_minutes, gate_status from dq_export_gate").fetchone() == (30, "BLOCKED")
    phase6d.finalize_quality_gate_phase6d(con, "RUN_TEST")
    row = con.execute("select exact_overlap_seconds, exact_overlap_minutes from dq_export_gate").fetchone()
    assert row == (1800, 30.0)


@pytest.mark.integration
def test_quality_gate_does_not_count_direct_adjacency_as_overlap(con):
    rows = [
        movement(1, transport_number="TR-A", period_start_utc=datetime(2026, 6, 1, 10), period_end_utc=datetime(2026, 6, 1, 11), actual_departure_ts=datetime(2026, 6, 1, 10), actual_arrival_ts=datetime(2026, 6, 1, 11), sequence_ts=datetime(2026, 6, 1, 10)),
        movement(2, transport_number="TR-B", period_start_utc=datetime(2026, 6, 1, 11), period_end_utc=datetime(2026, 6, 1, 12), actual_departure_ts=datetime(2026, 6, 1, 11), actual_arrival_ts=datetime(2026, 6, 1, 12), sequence_ts=datetime(2026, 6, 1, 11)),
    ]
    prepare_gate(con, rows)
    assert con.execute("select overlap_minutes, gate_status from dq_export_gate").fetchone() == (0, "READY")


@pytest.mark.rules
def test_r016_gap_only_blocked_day_becomes_visible_manual_review(con):
    create_findings_shell(con)
    create_rule_catalog_shell(con)
    con.execute("""
        create table dq_export_gate (
            run_id varchar, loco_no varchar, coverage_date date, assigned_minutes bigint,
            unresolved_gap_minutes bigint, error_findings bigint, manual_review_findings bigint,
            overlap_minutes bigint, long_gap_rows bigint, gate_status varchar
        )
    """)
    con.execute("insert into dq_export_gate values ('RUN_TEST','9180','2026-06-01',0,60,0,0,0,0,'BLOCKED')")
    phase6d.insert_gap_only_day_findings_phase6d(con, "RUN_TEST")
    row = con.execute("select rule_id, severity, row_type from dq_findings").fetchone()
    assert row == ("R016", "MANUAL_REVIEW", "GAP_DAY")
    assert con.execute("select count(*) from cfg_dq_rule_catalog where rule_id='R016'").fetchone()[0] == 1
