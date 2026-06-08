from __future__ import annotations

"""Isolierte DuckDB-Fachtests fuer Phase 6D."""

import sys
from pathlib import Path

import duckdb

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from rule_engine_hardening_phase6d import (  # noqa: E402
    finalize_quality_gate_phase6d,
    insert_gap_only_day_findings_phase6d,
)


def fixture() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    con.execute("""
        create table cfg_dq_rule_catalog (
          rule_id varchar, rule_group varchar, severity_policy varchar,
          message_template varchar, active_flag boolean
        );
        create table dq_findings (
          run_id varchar, severity varchar, rule_id varchar, rule_group varchar,
          loco_no varchar, transport_number varchar, performing_ru varchar,
          row_type varchar, movement_sequence_no bigint, period_start_utc timestamp,
          period_end_utc timestamp, message varchar, suggested_action varchar,
          status varchar, source_table varchar, source_row_id bigint,
          overlap_with_transport_number varchar
        );
        create table dq_run_metadata (error_cutoff_utc timestamp);
        insert into dq_run_metadata values (timestamp '2026-06-07 00:00:00');
        create table dq_export_gate (
          run_id varchar, loco_no varchar, coverage_date date, assigned_minutes bigint,
          unresolved_gap_minutes bigint, overlap_minutes bigint,
          long_gap_rows bigint, error_findings bigint, manual_review_findings bigint,
          gate_status varchar, gate_reason varchar
        );
        insert into dq_export_gate values
          ('run','L-GAP',date '2026-06-06',0,30,0,0,0,0,'BLOCKED','Ungeklaerte GAP-Minuten=30'),
          ('run','L-OVER',date '2026-06-06',60,0,15,0,0,0,'BLOCKED','Overlap-Minuten=15');
        create table core_loco_day_coverage as select * from dq_export_gate;
        create table dq_export_gate_ru as
          select *, 'RU'::varchar as performing_ru from dq_export_gate;
        create table core_usage_assignment_segment_movements (
          loco_no varchar, de_period_start_utc timestamp, de_period_end_utc timestamp
        );
        insert into core_usage_assignment_segment_movements values
          ('L-OVER', timestamp '2026-06-06 10:00:00', timestamp '2026-06-06 11:00:00'),
          ('L-OVER', timestamp '2026-06-06 10:50:00', timestamp '2026-06-06 11:10:00');
    """)
    return con


def main() -> int:
    con = fixture()
    insert_gap_only_day_findings_phase6d(con, "run")
    r016 = con.execute("select count(*) from dq_findings where rule_id='R016'").fetchone()[0]
    assert r016 == 1, r016
    finalize_quality_gate_phase6d(con, "run")
    exact = con.execute("""
      select exact_overlap_seconds, exact_overlap_minutes
      from dq_phase6d_exact_overlap_days
      where loco_no='L-OVER' and coverage_date=date '2026-06-06'
    """).fetchone()
    assert exact == (600, 10.0), exact
    gate = con.execute("""
      select exact_overlap_seconds, exact_overlap_minutes, gate_reason
      from dq_export_gate where loco_no='L-OVER'
    """).fetchone()
    assert gate[0] == 600 and gate[1] == 10.0, gate
    assert "Tatsaechliche Ueberschneidung=10.0 Minuten" in gate[2], gate[2]
    print("OK: Phase-6D-Logiktests erfolgreich.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
