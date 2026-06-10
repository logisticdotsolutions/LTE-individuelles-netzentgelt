from __future__ import annotations

from datetime import date
from pathlib import Path
import sys

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from export_exception_query_module import list_required_export_blockers  # noqa: E402


def test_multi_day_gap_creates_one_root_exception(tmp_path: Path) -> None:
    db_path = tmp_path / "netzentgelt.duckdb"
    con = duckdb.connect(str(db_path))
    try:
        con.execute(
            """
            create table dq_export_gate_ru (
                loco_no varchar,
                performing_ru varchar,
                coverage_date date,
                gate_reason varchar,
                gate_status varchar
            )
            """
        )
        con.execute(
            """
            insert into dq_export_gate_ru values
                ('91806189201-7', 'LTE DE - LTE Germany GmbH', date '2026-06-07', 'GAPs über 8h=1', 'BLOCKED'),
                ('91806189201-7', 'LTE DE - LTE Germany GmbH', date '2026-06-08', 'GAPs über 8h=1', 'BLOCKED')
            """
        )
        con.execute(
            """
            create table dq_global_export_blockers (
                blocker_date date,
                rule_id varchar,
                transport_number varchar,
                performing_ru varchar,
                message varchar,
                gate_status varchar
            )
            """
        )
        con.execute(
            """
            create table dq_findings (
                rule_id varchar,
                loco_no varchar,
                performing_ru varchar,
                period_start_utc timestamp,
                period_end_utc timestamp,
                message varchar,
                severity varchar
            )
            """
        )
        con.execute(
            """
            create table core_loco_timeline (
                row_type varchar,
                loco_no varchar,
                gap_relevant_de boolean,
                gap_time_basis_safe boolean,
                period_start_utc timestamp,
                period_end_utc timestamp,
                gap_duration_minutes bigint,
                dq_message varchar
            )
            """
        )
        con.execute(
            """
            insert into core_loco_timeline values (
                'GAP',
                '91806189201-7',
                true,
                true,
                timestamp '2026-06-06 16:00:00',
                timestamp '2026-06-08 11:00:00',
                2580,
                'Unterbrochene Ortskette'
            )
            """
        )
    finally:
        con.close()

    blockers = list_required_export_blockers(
        db_path=db_path,
        performing_ru_values=("LTE DE - LTE Germany GmbH",),
        date_from=date(2026, 6, 7),
        date_to=date(2026, 6, 8),
    )

    assert len(blockers) == 1
    blocker = blockers[0]
    assert blocker.blocker_type == "ROOT_GAP"
    assert blocker.rule_id == "R010"
    assert blocker.loco_no == "91806189201-7"
    assert blocker.performing_ru == ""
    assert blocker.period_start_utc == "2026-06-06 16:00:00"
    assert blocker.period_end_utc == "2026-06-08 11:00:00"
