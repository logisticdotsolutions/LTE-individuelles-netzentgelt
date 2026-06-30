from __future__ import annotations

from pathlib import Path
import sys

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from sitecustomize import _ensure_gate_finding_columns  # noqa: E402


def test_gate_finding_columns_are_added_when_schema_is_missing_warning_findings():
    con = duckdb.connect(database=":memory:")
    try:
        con.execute(
            """
            create table core_loco_day_coverage (
                loco_no varchar,
                coverage_date date,
                error_findings bigint
            )
            """
        )
        con.execute("insert into core_loco_day_coverage values ('L1', date '2026-06-28', null)")
        con.execute(
            """
            create table dq_export_gate (
                loco_no varchar,
                coverage_date date,
                error_findings bigint
            )
            """
        )

        _ensure_gate_finding_columns(con)

        coverage_columns = {row[0] for row in con.execute('describe core_loco_day_coverage').fetchall()}
        export_columns = {row[0] for row in con.execute('describe dq_export_gate').fetchall()}

        expected = {
            "error_findings",
            "manual_review_findings",
            "warning_findings",
            "info_findings",
            "long_gap_rows",
            "not_export_ready_movement_rows",
        }
        assert expected.issubset(coverage_columns)
        assert expected.issubset(export_columns)
        assert con.execute("select warning_findings from core_loco_day_coverage").fetchone()[0] == 0
        assert con.execute("select error_findings from core_loco_day_coverage").fetchone()[0] == 0
    finally:
        con.close()
