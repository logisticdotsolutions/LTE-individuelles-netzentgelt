from __future__ import annotations

import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD_SCRIPTS = ROOT / "payload" / "scripts"
sys.path.insert(0, str(PAYLOAD_SCRIPTS))

from rule_engine_hardening_phase6b import (  # noqa: E402
    apply_core_assignment_fallbacks,
    harden_findings_and_export_policy,
)


def setup_db():
    con = duckdb.connect(":memory:")
    con.execute("""
        create macro normalize_company_name(value) as
            regexp_replace(lower(coalesce(cast(value as varchar), '')), '[^a-z0-9]+', '', 'g')
    """)
    con.execute("""
        create table cfg_market_partner_mapping_effective (
            role_code varchar,
            source_value_normalized varchar,
            market_partner_id varchar
        )
    """)
    con.execute("""
        create table cfg_market_partner_role_effective (
            role_code varchar,
            company_name_normalized varchar,
            market_partner_id varchar
        )
    """)
    con.execute("""
        insert into cfg_market_partner_role_effective values
          ('ANE_TENS', normalize_company_name('Alpha Trains Luxembourg'), 'HOLDER_ALPHA'),
          ('ANE_TENS', normalize_company_name('LTE Germany GmbH'), 'WRONG_RU_HOLDER')
    """)
    con.execute("""
        create table cfg_dq_rule_catalog (
            rule_id varchar, rule_group varchar, severity_policy varchar,
            description varchar, active_flag boolean
        )
    """)
    con.execute("""
        insert into cfg_dq_rule_catalog values
          ('R002','TIME_QUALITY','INFO','ActualDeparture fehlt',true),
          ('R003','TIME_QUALITY','INFO','ActualArrival fehlt',true)
    """)
    con.execute("""
        create table dq_run_metadata (
            run_id varchar,
            source_snapshot_at_utc timestamp,
            error_cutoff_utc timestamp,
            calculated_at_utc timestamp
        )
    """)
    con.execute("""
        insert into dq_run_metadata values
          ('RUN_TEST', timestamp '2026-06-08 12:00:00', timestamp '2026-06-07 12:00:00', current_timestamp)
    """)
    con.execute("""
        create table core_loco_timeline (
            run_id varchar,
            row_type varchar,
            loco_no varchar,
            transport_number varchar,
            performing_ru varchar,
            movement_sequence_no bigint,
            period_start_utc timestamp,
            period_end_utc timestamp,
            sequence_ts timestamp,
            actual_departure_ts timestamp,
            actual_arrival_ts timestamp,
            holder_name varchar,
            holder_market_partner_id varchar,
            holder_market_partner_id_source varchar,
            performing_ru_marktpartner_id varchar,
            user_vens varchar,
            report_scope varchar,
            needs_manual_review boolean,
            dq_severity varchar,
            dq_message varchar,
            export_ready boolean,
            source_table varchar,
            source_row_id bigint
        )
    """)
    # A/B/C: overlap case. A is long interval, B and C must both receive R011.
    # D: holder missing => visible R013.
    # E: dummy loco => visible R014.
    # F: fresh incomplete interval => INFO only and not export_blocking.
    con.execute("""
        insert into core_loco_timeline values
          ('RUN_TEST','MOVEMENT','L1','T_A','LTE Germany GmbH',1,timestamp '2026-06-01 00:00',timestamp '2026-06-01 10:00',timestamp '2026-06-01 00:00',timestamp '2026-06-01 00:00',timestamp '2026-06-01 10:00','Alpha Trains Luxembourg','WRONG_RU_HOLDER','MAPPING_IMPORT','RU_MP',null,'IN_REPORT',false,'','',false,'raw_locomotivemovement',1),
          ('RUN_TEST','MOVEMENT','L1','T_B','LTE Germany GmbH',2,timestamp '2026-06-01 01:00',timestamp '2026-06-01 02:00',timestamp '2026-06-01 01:00',timestamp '2026-06-01 01:00',timestamp '2026-06-01 02:00','Alpha Trains Luxembourg','WRONG_RU_HOLDER','MAPPING_IMPORT','RU_MP',null,'IN_REPORT',false,'','',false,'raw_locomotivemovement',2),
          ('RUN_TEST','MOVEMENT','L1','T_C','LTE Germany GmbH',3,timestamp '2026-06-01 03:00',timestamp '2026-06-01 04:00',timestamp '2026-06-01 03:00',timestamp '2026-06-01 03:00',timestamp '2026-06-01 04:00','Alpha Trains Luxembourg','WRONG_RU_HOLDER','MAPPING_IMPORT','RU_MP',null,'IN_REPORT',false,'','',false,'raw_locomotivemovement',3),
          ('RUN_TEST','MOVEMENT','L2','T_D','LTE Germany GmbH',1,timestamp '2026-06-01 05:00',timestamp '2026-06-01 06:00',timestamp '2026-06-01 05:00',timestamp '2026-06-01 05:00',timestamp '2026-06-01 06:00',null,null,'UNRESOLVED','RU_MP',null,'IN_REPORT',false,'','',false,'raw_locomotivemovement',4),
          ('RUN_TEST','MOVEMENT','00000000000-0','T_E','LTE Germany GmbH',1,timestamp '2026-06-01 07:00',timestamp '2026-06-01 08:00',timestamp '2026-06-01 07:00',timestamp '2026-06-01 07:00',timestamp '2026-06-01 08:00','Alpha Trains Luxembourg','WRONG_RU_HOLDER','MAPPING_IMPORT','RU_MP',null,'IN_REPORT',false,'','',false,'raw_locomotivemovement',5),
          ('RUN_TEST','MOVEMENT','L3','T_F','LTE Germany GmbH',1,timestamp '2026-06-08 08:00',null,timestamp '2026-06-08 08:00',timestamp '2026-06-08 08:00',null,'Alpha Trains Luxembourg','WRONG_RU_HOLDER','MAPPING_IMPORT','RU_MP',null,'IN_REPORT',false,'','',false,'raw_locomotivemovement',6)
    """)
    con.execute("""
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
    """)
    con.execute("""
        insert into dq_findings values
          ('RUN_TEST','ERROR','R011','TIMELINE','L1','T_C','LTE Germany GmbH','MOVEMENT',3,timestamp '2026-06-01 03:00',timestamp '2026-06-01 04:00','old lag finding','old','open','raw_locomotivemovement',3,null),
          ('RUN_TEST','INFO','R003','TIME_QUALITY','L3','T_F','LTE Germany GmbH','MOVEMENT',1,timestamp '2026-06-08 08:00',null,'ActualArrival fehlt oder ist ungültig.','Nur dokumentieren.','info','raw_locomotivemovement',6,null)
    """)
    return con


def main() -> int:
    con = setup_db()
    apply_core_assignment_fallbacks(con, "RUN_TEST")
    harden_findings_and_export_policy(con, "RUN_TEST")

    row = con.execute("""
        select holder_market_partner_id, holder_market_partner_id_source, user_vens, export_ready
        from core_loco_timeline where source_row_id = 1
    """).fetchone()
    assert row == ('HOLDER_ALPHA', 'OFFICIAL_NAME_EXACT', 'LTE Germany GmbH', True), row

    r011 = con.execute("select transport_number, overlap_with_transport_number from dq_findings where rule_id='R011' order by transport_number").fetchall()
    assert r011 == [('T_B', 'T_A'), ('T_C', 'T_A')], r011

    assert con.execute("select count(*) from dq_findings where rule_id='R013' and transport_number='T_D'").fetchone()[0] == 1
    assert con.execute("select count(*) from dq_findings where rule_id='R014' and transport_number='T_E'").fetchone()[0] == 1

    fresh = con.execute("select export_ready, export_blocking, dq_severity from core_loco_timeline where transport_number='T_F'").fetchone()
    assert fresh == (False, False, 'INFO'), fresh

    blockers = con.execute("select transport_number from dq_rule_engine_hardening_blockers order by transport_number").fetchall()
    assert ('T_D',) in blockers, blockers
    assert ('T_E',) in blockers, blockers
    assert ('T_F',) not in blockers, blockers

    assert con.execute("select count(*) from dq_rule_engine_hardening_audit").fetchone()[0] >= 7
    con.close()
    print('OK: Phase-6B-Logiktests erfolgreich.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
