from __future__ import annotations

"""Regressionstest fuer den Phase-6D-Verify-Hotfix gegen produktionsnahe Gate-Spalten."""

import sys
import tempfile
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from verify_rule_engine_hardening_phase6d import verify  # noqa: E402


def build_fixture(path: Path, missing_exact: bool = False) -> None:
    con = duckdb.connect(str(path))
    try:
        con.execute("""
            create table dq_findings (rule_id varchar);
            insert into dq_findings values ('R016');
            create table dq_export_gate (
              loco_no varchar, coverage_date date, gate_status varchar,
              assigned_minutes bigint, unresolved_gap_minutes bigint,
              error_findings bigint, manual_review_findings bigint,
              overlap_minutes bigint, long_gap_rows bigint,
              exact_overlap_seconds bigint, exact_overlap_minutes double
            );
            create table core_loco_day_coverage as select * from dq_export_gate where 1=0;
            create table dq_export_gate_ru (
              loco_no varchar, coverage_date date, gate_status varchar,
              assigned_minutes bigint, unresolved_gap_minutes bigint,
              error_findings bigint, manual_review_findings bigint,
              overlap_minutes bigint, long_gap_rows bigint,
              exact_overlap_seconds bigint, exact_overlap_minutes double
            );
            create table dq_phase6d_exact_overlap_days (loco_no varchar, coverage_date date);
            create table dq_rule_engine_hardening_phase6d_audit (metric varchar);
            insert into dq_rule_engine_hardening_phase6d_audit values ('fixture');
            create table core_loco_stand_candidates (loco_no varchar);
            create table dq_phase6c_gap_context_review (loco_no varchar);
            create table dq_phase6c_uncertain_gaps (loco_no varchar);
        """)
        exact_value = "null" if missing_exact else "10.0"
        con.execute(f"""
            insert into dq_export_gate values
              ('L-OVER', date '2026-06-06', 'BLOCKED', 60, 0, 0, 0, 15, 0, 600, {exact_value});
            insert into dq_export_gate_ru values
              ('L-OVER', date '2026-06-06', 'BLOCKED', 60, 0, 0, 0, 15, 0, 600, {exact_value});
            insert into core_loco_day_coverage values
              ('L-OVER', date '2026-06-06', 'BLOCKED', 60, 0, 0, 0, 15, 0, 600, {exact_value});
            insert into dq_phase6d_exact_overlap_days values ('L-OVER', date '2026-06-06');
        """)
    finally:
        con.close()


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="phase6d_verify_hotfix_") as temp:
        good = Path(temp) / "good.duckdb"
        build_fixture(good, missing_exact=False)
        verify(good)
        bad = Path(temp) / "bad.duckdb"
        build_fixture(bad, missing_exact=True)
        try:
            verify(bad)
        except RuntimeError as exc:
            assert "Overlap-Tage ohne exakte Dauer" in str(exc), str(exc)
        else:
            raise AssertionError("Negativtest haette fehlschlagen muessen.")
    print("OK: Phase-6D-Verify-Hotfix-Regressionstest erfolgreich.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
