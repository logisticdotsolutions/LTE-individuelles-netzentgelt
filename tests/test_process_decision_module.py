from __future__ import annotations

import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from process_decision_module import build_process_decision_layer  # noqa: E402


def _prepare_db():
    con = duckdb.connect(":memory:")
    con.execute(
        """
        create table core_usage_assignment_segments (
            run_id varchar,
            loco_no varchar,
            usage_segment_no bigint,
            usage_segment_id varchar,
            tfze_or_tens varchar,
            performing_ru varchar,
            segment_start_utc timestamp,
            segment_end_utc timestamp,
            first_actual_departure_utc timestamp,
            last_actual_arrival_utc timestamp,
            movement_count bigint,
            export_ready_movement_rows bigint,
            export_blocking_movement_rows bigint,
            user_vens varchar,
            holder_name varchar,
            holder_market_partner_id varchar
        )
        """
    )
    con.executemany(
        """
        insert into core_usage_assignment_segments values (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        [
            (
                "RUN_BASE",
                "9180 1293 001-1",
                1,
                "9180 1293 001-1:1",
                "TENS001",
                "LTE NL - LTE Netherlands B.V.",
                "2026-07-01 08:00:00",
                "2026-07-01 10:00:00",
                "2026-07-01 08:00:00",
                "2026-07-01 10:00:00",
                1,
                1,
                0,
                "VENS_NL",
                "LTE Holding GmbH",
                "1900100000001",
            ),
            (
                "RUN_BASE",
                "9180 1293 002-9",
                1,
                "9180 1293 002-9:1",
                "TENS002",
                "LTE NL - LTE Netherlands B.V.",
                "2026-07-01 11:00:00",
                "2026-07-01 12:00:00",
                "2026-07-01 11:00:00",
                "2026-07-01 12:00:00",
                1,
                1,
                0,
                "VENS_NL",
                "LTE NL - LTE Netherlands B.V.",
                "1900100000002",
            ),
            (
                "RUN_BASE",
                "9180 1293 003-7",
                1,
                "9180 1293 003-7:1",
                "TENS003",
                "LTE DE - LTE Germany GmbH",
                "2026-07-01 13:00:00",
                "2026-07-01 14:00:00",
                "2026-07-01 13:00:00",
                "2026-07-01 14:00:00",
                1,
                1,
                0,
                "VENS_DE",
                "BRCE GmbH",
                "1900100000003",
            ),
            (
                "RUN_BASE",
                "9180 1293 004-5",
                1,
                "9180 1293 004-5:1",
                "TENS004",
                None,
                "2026-07-01 15:00:00",
                "2026-07-01 16:00:00",
                "2026-07-01 15:00:00",
                "2026-07-01 16:00:00",
                1,
                0,
                1,
                None,
                "LTE Holding GmbH",
                None,
            ),
        ],
    )
    con.execute(
        """
        create table dq_export_gate_ru (
            loco_no varchar,
            performing_ru varchar,
            coverage_date date,
            gate_status varchar
        )
        """
    )
    con.execute(
        """
        create table dq_global_export_blockers (
            blocker_date date,
            gate_status varchar
        )
        """
    )
    con.execute(
        """
        create table core_loco_timeline (
            run_id varchar,
            row_type varchar,
            loco_no varchar,
            performing_ru varchar,
            faulty_dir varchar,
            clean_dir varchar,
            report_scope varchar,
            actual_arrival_ts timestamp,
            actual_departure_ts timestamp,
            sequence_ts timestamp
        )
        """
    )
    return con


def test_process_decision_classifies_wim_cases_and_export_message_type():
    con = _prepare_db()

    build_process_decision_layer(con, "RUN_TEST")

    rows = {
        row[0]: row[1:]
        for row in con.execute(
            """
            select loco_no, process_category, process_case, process_message_type, process_owner
            from core_process_decisions
            order by loco_no
            """
        ).fetchall()
    }

    assert rows["9180 1293 001-1"] == (
        "UEBERGABE",
        "UEBERGABE_4_LTE_HOLDING_AN_LTE_NL",
        "Übergabemeldung",
        "LTE Holding",
    )
    assert rows["9180 1293 002-9"] == (
        "ZUORDNUNG",
        "UEBERGABE_2_LTE_NL_SELF",
        "Keine Aktion",
        "LTE Netherlands",
    )
    assert rows["9180 1293 003-7"] == (
        "UEBERGABE",
        "UEBERGABE_Z_ANDERE_EVU_AN_LTE_GE",
        "Übernahmeanfrage",
        "LTE Germany",
    )
    assert rows["9180 1293 004-5"] == (
        "MANUELLE_PRUEFUNG",
        "MANUELLE_PRUEFUNG",
        "Manuelle Prüfung",
        "Manuelle Prüfung",
    )

    export_row = con.execute(
        """
        select "Übernahmeanfrage oder Übergabemeldung?", "Prozessfall"
        from export_nutzungsmeldung
        where "TfzE oder tEns*" = 'TENS001'
        """
    ).fetchone()

    assert export_row == (
        "Übergabemeldung",
        "UEBERGABE_4_LTE_HOLDING_AN_LTE_NL",
    )


def test_process_decision_builds_event_decision_table():
    con = _prepare_db()
    con.execute(
        """
        insert into core_loco_timeline values (
            'RUN_BASE', 'MOVEMENT', '9180 1293 010-2',
            'LTE DE - LTE Germany GmbH', '', 'E', 'IN_REPORT',
            '2026-07-02 09:00:00', '2026-07-02 08:00:00', '2026-07-02 08:00:00'
        )
        """
    )

    build_process_decision_layer(con, "RUN_TEST")

    event_row = con.execute(
        """
        select event_type, event_process_case, event_process_owner
        from core_event_process_decisions
        where loco_no = '9180 1293 010-2'
        """
    ).fetchone()

    assert event_row == ("einfahrend", "EREIGNIS_6_LTE_GE", "LTE Germany")
