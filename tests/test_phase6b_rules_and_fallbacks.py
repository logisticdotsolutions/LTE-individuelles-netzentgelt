from __future__ import annotations

from datetime import datetime

import pytest

import error_rules
import rule_engine_hardening_phase6b as phase6b
import run_all
from tests.support.builders import build_base_findings, insert_row, movement, prepare_base


def create_mapping_tables(con) -> None:
    run_all.create_company_normalization_macro(con)
    con.execute("""
        create or replace table cfg_market_partner_mapping_effective (
            role_code varchar, source_value_normalized varchar, source_value varchar,
            official_company_name varchar, market_partner_id varchar,
            match_method varchar, match_score double
        )
    """)
    con.execute("""
        create or replace table cfg_market_partner_role_effective (
            role_code varchar, company_name_normalized varchar,
            company_name_official varchar, market_partner_id varchar
        )
    """)


@pytest.mark.rules
def test_r002_r003_become_manual_review_after_24h_cutoff(con):
    rows = [
        movement(1, period_start_utc=None, actual_departure_ts=None, period_end_utc=datetime(2026, 6, 1, 11), transport_number="TR-OLD-MISSING-DEP"),
        movement(2, period_start_utc=datetime(2026, 6, 1, 12), period_end_utc=None, actual_arrival_ts=None, sequence_ts=datetime(2026, 6, 1, 12), transport_number="TR-OLD-MISSING-ARR"),
    ]
    build_base_findings(con, rows)
    phase6b.harden_findings_and_export_policy(con, "RUN_TEST")
    result = con.execute("select rule_id, severity from dq_findings where rule_id in ('R002','R003') order by rule_id").fetchall()
    assert result == [("R002", "MANUAL_REVIEW"), ("R003", "MANUAL_REVIEW")]


@pytest.mark.rules
def test_missing_arrival_inside_24h_remains_info_and_nonblocking(con):
    row = movement(
        1,
        period_start_utc=datetime(2026, 6, 8, 10),
        period_end_utc=None,
        actual_departure_ts=datetime(2026, 6, 8, 10),
        actual_arrival_ts=None,
        sequence_ts=datetime(2026, 6, 8, 10),
        transport_number="TR-FRESH",
    )
    build_base_findings(con, [row])
    phase6b.harden_findings_and_export_policy(con, "RUN_TEST")
    severity = con.execute("select severity from dq_findings where rule_id='R003'").fetchone()[0]
    blocking = con.execute("select export_blocking from core_loco_timeline where transport_number='TR-FRESH'").fetchone()[0]
    assert severity == "INFO"
    assert blocking is False


@pytest.mark.rules
def test_r011_real_overlap_but_not_direct_adjacency(con):
    rows = [
        movement(1, transport_number="TR-A", period_start_utc=datetime(2026, 6, 1, 10), period_end_utc=datetime(2026, 6, 1, 11), sequence_ts=datetime(2026, 6, 1, 10)),
        movement(2, transport_number="TR-B", period_start_utc=datetime(2026, 6, 1, 11), period_end_utc=datetime(2026, 6, 1, 12), sequence_ts=datetime(2026, 6, 1, 11)),
        movement(3, transport_number="TR-C", period_start_utc=datetime(2026, 6, 1, 11, 30), period_end_utc=datetime(2026, 6, 1, 13), sequence_ts=datetime(2026, 6, 1, 11, 30)),
    ]
    build_base_findings(con, rows)
    phase6b.harden_findings_and_export_policy(con, "RUN_TEST")
    result = con.execute("select transport_number, overlap_with_transport_number from dq_findings where rule_id='R011' order by transport_number").fetchall()
    assert result == [("TR-C", "TR-B")]


@pytest.mark.rules
def test_r013_missing_holder_becomes_visible_manual_review(con):
    build_base_findings(con, [movement(1, holder_name=None)])
    phase6b.harden_findings_and_export_policy(con, "RUN_TEST")
    assert con.execute("select severity from dq_findings where rule_id='R013'").fetchone()[0] == "MANUAL_REVIEW"


@pytest.mark.rules
def test_r014_dummy_loco_is_visible_in_timeline(con):
    build_base_findings(con, [movement(1, loco_no="00000000000-0", tfze_or_tens="00000000000-0")])
    phase6b.harden_findings_and_export_policy(con, "RUN_TEST")
    assert con.execute("select severity from dq_findings where rule_id='R014'").fetchone()[0] == "ERROR"


@pytest.mark.integration
def test_holder_resolution_uses_holder_and_user_vens_falls_back_to_performing_ru(con):
    prepare_base(con, [movement(1, holder_name="Holder Rail GmbH", performing_ru="Operating RU", user_vens=None)])
    create_mapping_tables(con)
    con.execute("insert into cfg_market_partner_mapping_effective values ('ANE_TENS', normalize_company_name('Holder Rail GmbH'), 'Holder Rail GmbH', 'Holder Rail GmbH', 'MP-HOLDER', 'fixture', 1.0)")
    con.execute("insert into cfg_market_partner_mapping_effective values ('ANE_TENS', normalize_company_name('Operating RU'), 'Operating RU', 'Wrong RU', 'MP-WRONG', 'fixture', 1.0)")
    phase6b.apply_core_assignment_fallbacks(con, "RUN_TEST")
    row = con.execute("select holder_market_partner_id, holder_market_partner_id_source, user_vens from core_loco_timeline").fetchone()
    assert row == ("MP-HOLDER", "MAPPING_IMPORT", "Operating RU")


@pytest.mark.integration
def test_holder_name_is_explicit_fallback_when_no_mapping_exists(con):
    prepare_base(con, [movement(1, holder_name="Fallback Holder", performing_ru="Fallback RU", user_vens=None)])
    create_mapping_tables(con)
    phase6b.apply_core_assignment_fallbacks(con, "RUN_TEST")
    row = con.execute("select holder_market_partner_id, holder_market_partner_id_source, user_vens from core_loco_timeline").fetchone()
    assert row == ("Fallback Holder", "FALLBACK_HOLDER_NAME", "Fallback RU")
