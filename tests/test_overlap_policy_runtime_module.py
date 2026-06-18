from __future__ import annotations

from pathlib import Path
import sys

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from overlap_policy_runtime_module import apply_overlap_policy_diff_evu_only  # noqa: E402


def _setup(con) -> None:
    con.execute(
        """
        create table core_loco_timeline (
            row_type varchar,
            report_scope varchar,
            loco_no varchar,
            transport_number varchar,
            performing_ru varchar,
            period_start_utc timestamp,
            period_end_utc timestamp,
            source_table varchar,
            source_row_id bigint
        )
        """
    )
    con.execute(
        """
        create table dq_findings (
            run_id varchar,
            severity varchar,
            rule_id varchar,
            rule_group varchar,
            loco_no varchar,
            transport_number varchar,
            performing_ru varchar,
            row_type varchar,
            movement_sequence_no bigint,
            period_start_utc timestamp,
            period_end_utc timestamp,
            message varchar,
            suggested_action varchar,
            status varchar,
            source_table varchar,
            source_row_id bigint,
            overlap_with_transport_number varchar
        )
        """
    )
    con.execute(
        """
        create table core_usage_assignment_segment_movements (
            loco_no varchar,
            performing_ru varchar,
            de_period_start_utc timestamp,
            de_period_end_utc timestamp,
            source_row_id bigint
        )
        """
    )
    con.execute("create table dq_run_metadata(error_cutoff_utc timestamp)")
    con.execute("insert into dq_run_metadata values ('2026-06-18 00:00:00')")
    for table in ["core_loco_day_coverage", "dq_export_gate", "dq_export_gate_ru"]:
        con.execute(
            f"""
            create table {table} (
                loco_no varchar,
                coverage_date date,
                assigned_minutes bigint,
                unresolved_gap_minutes bigint,
                overlap_minutes bigint,
                error_findings bigint,
                manual_review_findings bigint,
                warning_findings bigint,
                info_findings bigint,
                long_gap_rows bigint,
                not_export_ready_movement_rows bigint,
                gate_status varchar,
                gate_reason varchar,
                exact_overlap_seconds bigint,
                exact_overlap_minutes double
            )
            """
        )


def test_same_evu_overlap_is_removed_and_does_not_block_gate() -> None:
    con = duckdb.connect(":memory:")
    _setup(con)
    con.execute(
        """
        insert into core_loco_timeline values
        ('MOVEMENT','IN_REPORT','L1','T1','LTE DE','2026-06-16 10:00:00','2026-06-16 11:00:00','raw',1),
        ('MOVEMENT','IN_REPORT','L1','T2','LTE DE','2026-06-16 10:30:00','2026-06-16 11:30:00','raw',2)
        """
    )
    con.execute(
        """
        insert into core_usage_assignment_segment_movements values
        ('L1','LTE DE','2026-06-16 10:00:00','2026-06-16 11:00:00',1),
        ('L1','LTE DE','2026-06-16 10:30:00','2026-06-16 11:30:00',2)
        """
    )
    con.execute(
        """
        insert into dq_findings values
        ('RUN','ERROR','R011','TIMELINE','L1','T2','LTE DE','MOVEMENT',null,'2026-06-16 10:30:00','2026-06-16 11:30:00','overlap','check','open','raw',2,'T1')
        """
    )
    for table in ["core_loco_day_coverage", "dq_export_gate", "dq_export_gate_ru"]:
        con.execute(f"insert into {table} values ('L1','2026-06-16',60,0,30,0,0,0,0,0,0,'BLOCKED','Overlap-Minuten=30',1800,30.0)")

    apply_overlap_policy_diff_evu_only(con, "RUN")

    assert con.execute("select count(*) from dq_findings where rule_id='R011'").fetchone()[0] == 0
    assert con.execute("select count(*) from dq_phase6d_exact_overlap_days").fetchone()[0] == 0
    assert con.execute("select overlap_minutes, gate_status from dq_export_gate").fetchone() == (0, "READY")


def test_different_evu_overlap_remains_report_relevant() -> None:
    con = duckdb.connect(":memory:")
    _setup(con)
    con.execute(
        """
        insert into core_loco_timeline values
        ('MOVEMENT','IN_REPORT','L2','T1','LTE DE','2026-06-16 10:00:00','2026-06-16 11:00:00','raw',1),
        ('MOVEMENT','IN_REPORT','L2','T2','LTE NL','2026-06-16 10:30:00','2026-06-16 11:30:00','raw',2)
        """
    )
    con.execute(
        """
        insert into core_usage_assignment_segment_movements values
        ('L2','LTE DE','2026-06-16 10:00:00','2026-06-16 11:00:00',1),
        ('L2','LTE NL','2026-06-16 10:30:00','2026-06-16 11:30:00',2)
        """
    )
    con.execute(
        """
        insert into dq_findings values
        ('RUN','ERROR','R011','TIMELINE','L2','T2','LTE NL','MOVEMENT',null,'2026-06-16 10:30:00','2026-06-16 11:30:00','overlap','check','open','raw',2,'T1')
        """
    )
    for table in ["core_loco_day_coverage", "dq_export_gate", "dq_export_gate_ru"]:
        con.execute(f"insert into {table} values ('L2','2026-06-16',60,0,0,0,0,0,0,0,0,'READY','',0,0.0)")

    apply_overlap_policy_diff_evu_only(con, "RUN")

    assert con.execute("select count(*) from dq_findings where rule_id='R011'").fetchone()[0] == 1
    assert con.execute("select exact_overlap_minutes from dq_phase6d_exact_overlap_days").fetchone()[0] == 30.0
    assert con.execute("select overlap_minutes, gate_status from dq_export_gate").fetchone() == (30, "BLOCKED")
