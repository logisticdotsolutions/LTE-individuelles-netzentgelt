from __future__ import annotations

from datetime import datetime

import pytest

import error_rules
from tests.support.builders import build_base_findings, gap, insert_row, movement, prepare_base


def rules(con, rule_id: str):
    return con.execute(
        "select severity, rule_id, row_type, loco_no, transport_number from dq_findings where rule_id=? order by severity, transport_number",
        [rule_id],
    ).fetchall()


@pytest.mark.rules
def test_rule_catalog_documents_r001_to_r012_and_explicit_inactive_policies(con):
    prepare_base(con)
    error_rules.build_rule_catalog(con)
    catalog = {row[0]: row[1:] for row in con.execute("select rule_id, severity_policy, active_flag from cfg_dq_rule_catalog").fetchall()}
    assert set(catalog) == {"R001", "R002", "R003", "R004", "R005", "R006", "R007", "R008", "R009", "R010", "R010.5", "R011", "R012"}
    assert catalog["R005"] == ("SEPARATE", False)
    assert catalog["R006"] == ("IGNORED", False)
    assert catalog["R007"] == ("IGNORED", False)
    assert catalog["R008"] == ("REMOVED", False)


@pytest.mark.rules
def test_r001_first_missing_anchor_is_info_but_later_missing_anchor_is_error(con):
    rows = [
        movement(1, sequence_ts=None, transport_number="TR-FIRST"),
        movement(2, sequence_ts=None, transport_number="TR-LATER", period_start_utc=datetime(2026, 6, 1, 12), period_end_utc=datetime(2026, 6, 1, 13)),
    ]
    build_base_findings(con, rows)
    result = con.execute("select transport_number, severity from dq_findings where rule_id='R001' order by transport_number").fetchall()
    assert result == [("TR-FIRST", "INFO"), ("TR-LATER", "ERROR")]


@pytest.mark.rules
def test_r002_and_r003_are_created_for_missing_time_boundaries(con):
    rows = [
        movement(1, period_start_utc=None, actual_departure_ts=None, transport_number="TR-NO-DEP"),
        movement(2, period_end_utc=None, actual_arrival_ts=None, transport_number="TR-NO-ARR", period_start_utc=datetime(2026, 6, 1, 12), sequence_ts=datetime(2026, 6, 1, 12)),
    ]
    build_base_findings(con, rows)
    assert rules(con, "R002") == [("INFO", "R002", "MOVEMENT", "91800000001-1", "TR-NO-DEP")]
    assert rules(con, "R003") == [("INFO", "R003", "MOVEMENT", "91800000001-1", "TR-NO-ARR")]


@pytest.mark.rules
def test_r004_departure_after_arrival_is_error(con):
    row = movement(1, period_start_utc=datetime(2026, 6, 1, 12), period_end_utc=datetime(2026, 6, 1, 11))
    build_base_findings(con, [row])
    assert len(rules(con, "R004")) == 1
    assert rules(con, "R004")[0][0] == "ERROR"


@pytest.mark.rules
def test_r009_missing_performing_ru_is_manual_review(con):
    build_base_findings(con, [movement(1, performing_ru=None)])
    assert len(rules(con, "R009")) == 1
    assert rules(con, "R009")[0][0] == "MANUAL_REVIEW"


@pytest.mark.rules
def test_r010_long_gap_and_r010_5_short_gap(con):
    rows = [gap(1, minutes=481, transport_number="TR-LONG"), gap(2, minutes=480, transport_number="TR-SHORT")]
    build_base_findings(con, rows)
    assert len(rules(con, "R010")) == 1
    assert len(rules(con, "R010.5")) == 1
    assert rules(con, "R010")[0][0] == "ERROR"
    assert rules(con, "R010.5")[0][0] == "INFO"


@pytest.mark.rules
def test_r011_detects_overlap_in_base_rule(con):
    rows = [
        movement(1, transport_number="TR-A", period_start_utc=datetime(2026, 6, 1, 10), period_end_utc=datetime(2026, 6, 1, 12), sequence_ts=datetime(2026, 6, 1, 10)),
        movement(2, transport_number="TR-B", period_start_utc=datetime(2026, 6, 1, 11), period_end_utc=datetime(2026, 6, 1, 13), sequence_ts=datetime(2026, 6, 1, 11)),
    ]
    build_base_findings(con, rows)
    assert len(rules(con, "R011")) == 1
    assert con.execute("select overlap_with_transport_number from dq_findings where rule_id='R011'").fetchone()[0] == "TR-A"


@pytest.mark.rules
def test_r012_raw_transportdetail_missing_loco_is_condensed(con):
    prepare_base(con)
    con.execute("insert into raw_transportdetail values ('TR-RAW', 'Planned', '1', 'DE', 'DE', '2026-06-01T10:00:00', '2026-06-01T11:00:00', null, 'Train movement')")
    con.execute("insert into raw_transportdetail values ('TR-RAW', 'Planned', '2', 'DE', 'DE', '2026-06-01T10:00:00', '2026-06-01T11:00:00', null, 'Train movement')")
    error_rules.build_findings(con, "RUN_TEST")
    result = con.execute("select count(*), max(message) from dq_findings where rule_id='R012' and source_table='raw_transportdetail'").fetchone()
    assert result[0] == 1
    assert "Betroffene Rohdatenzeilen: 2" in result[1]


@pytest.mark.rules
def test_r012_raw_locomotivemovement_dummy_is_detected(con):
    prepare_base(con)
    con.execute("insert into raw_locomotivemovement values ('00000000000-0', null, 'RU GmbH', '2026-06-01T10:00:00', '2026-06-01T11:00:00', 'DE', 'DE', 'TR-DUMMY', 'Holder', 'A', 'B')")
    error_rules.build_findings(con, "RUN_TEST")
    assert con.execute("select count(*) from dq_findings where rule_id='R012' and transport_number='TR-DUMMY'").fetchone()[0] == 1

@pytest.mark.rules
def test_r006_r007_r008_intentionally_do_not_create_findings_in_mvp(con):
    row = movement(1, user_vens=None, holder_market_partner_id=None, performing_ru_marktpartner_id=None, tfze_or_tens="91800000001-1")
    build_base_findings(con, [row])
    assert con.execute("select count(*) from dq_findings where rule_id in ('R006','R007','R008')").fetchone()[0] == 0
