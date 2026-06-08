from __future__ import annotations

from datetime import datetime

import pytest

import rule_engine_hardening_phase6c as phase6c
from tests.support.builders import (
    create_core_timeline,
    create_dq_metadata,
    create_findings_shell,
    create_rule_catalog_shell,
    ensure_phase6c_columns,
    gap,
    insert_row,
    movement,
)


@pytest.mark.integration
def test_de_relevance_expression_prefers_origin_destination_over_country(con):
    expr = phase6c._de_relevance_expr(["OriginCountryISO", "DestinationCountryISO", "Country"])
    con.execute("create table fixture (OriginCountryISO varchar, DestinationCountryISO varchar, Country varchar)")
    con.execute("insert into fixture values ('AT', 'AT', 'DE'), ('AT', 'DE', 'AT')")
    result = con.execute(f"select {expr} from fixture order by OriginCountryISO, DestinationCountryISO").fetchall()
    assert result == [(False,), (True,)]


@pytest.mark.integration
def test_gap_context_classification_and_cold_stand_candidate(con):
    create_core_timeline(con)
    first = movement(
        1,
        transport_number="TR-STAND-A",
        actual_departure_ts=datetime(2026, 6, 1, 1),
        actual_arrival_ts=datetime(2026, 6, 1, 2),
        period_start_utc=datetime(2026, 6, 1, 1),
        period_end_utc=datetime(2026, 6, 1, 2),
        sequence_ts=datetime(2026, 6, 1, 1),
        origin_name="Berlin",
        destination_name="Hamburg",
    )
    second = movement(
        2,
        transport_number="TR-STAND-B",
        actual_departure_ts=datetime(2026, 6, 1, 12),
        actual_arrival_ts=datetime(2026, 6, 1, 13),
        period_start_utc=datetime(2026, 6, 1, 12),
        period_end_utc=datetime(2026, 6, 1, 13),
        sequence_ts=datetime(2026, 6, 1, 12),
        origin_name="Hamburg",
        destination_name="Munich",
    )
    insert_row(con, "core_loco_timeline", first)
    insert_row(con, "core_loco_timeline", second)
    phase6c.prepare_timeline_context_phase6c(con, "RUN_TEST")
    row = con.execute("select location_name, stand_duration_minutes, stand_class from core_loco_stand_candidates").fetchone()
    assert row == ("Hamburg", 600, "POTENTIAL_COLD_STAND")


@pytest.mark.integration
def test_border_context_gap_is_audit_visible_but_not_automatically_blocking(con):
    create_core_timeline(con)
    insert_row(con, "core_loco_timeline", movement(1, origin_name="A", destination_name="B", de_event_label="Ausfahrt", clean_dir="A"))
    insert_row(
        con,
        "core_loco_timeline",
        movement(
            2,
            origin_name="C",
            destination_name="D",
            report_scope="NOT_IN_REPORT",
            de_event_label="Not in the Report",
            origin_country_iso="AT",
            destination_country_iso="AT",
            country="AT",
            period_start_utc=datetime(2026, 6, 1, 12),
            period_end_utc=datetime(2026, 6, 1, 13),
            actual_departure_ts=datetime(2026, 6, 1, 12),
            actual_arrival_ts=datetime(2026, 6, 1, 13),
            sequence_ts=datetime(2026, 6, 1, 12),
        ),
    )
    phase6c.prepare_timeline_context_phase6c(con, "RUN_TEST")
    row = con.execute("select gap_context_class from dq_phase6c_gap_context_review").fetchone()
    assert row == ("DE_TO_FOREIGN_CONTEXT_REVIEW",)


@pytest.mark.rules
def test_r015_uncertain_gap_old_is_manual_review(con):
    create_core_timeline(con)
    create_findings_shell(con)
    create_rule_catalog_shell(con)
    create_dq_metadata(con)
    con.execute("""
        create table dq_phase6c_uncertain_gaps (
            run_id varchar, loco_no varchar, transport_number varchar, next_transport_number varchar,
            destination_name varchar, next_origin_name varchar, actual_arrival_ts timestamp,
            next_actual_departure_ts timestamp, approximate_gap_start_utc timestamp,
            approximate_gap_end_utc timestamp, gap_context_class varchar, source_table varchar, source_row_id bigint
        )
    """)
    con.execute("insert into dq_phase6c_uncertain_gaps values ('RUN_TEST','9180','TR-A','TR-B','A','B',null,'2026-06-01 12:00:00','2026-06-01 10:00:00','2026-06-01 12:00:00','DE_CONTINUITY','raw_locomotivemovement',1)")
    phase6c._insert_r015_uncertain_gap_findings(con, "RUN_TEST")
    assert con.execute("select rule_id, severity from dq_findings").fetchone() == ("R015", "MANUAL_REVIEW")


@pytest.mark.integration
def test_central_de_segments_use_border_bounded_times(con):
    create_core_timeline(con)
    ensure_phase6c_columns(con)
    entry = movement(
        1,
        transport_number="TR-ENTRY",
        faulty_dir="E",
        actual_departure_ts=datetime(2026, 6, 1, 8),
        actual_arrival_ts=datetime(2026, 6, 1, 9),
        period_start_utc=datetime(2026, 6, 1, 8),
        period_end_utc=datetime(2026, 6, 1, 9),
        sequence_ts=datetime(2026, 6, 1, 9),
        export_ready=True,
    )
    exit_row = movement(
        2,
        transport_number="TR-EXIT",
        faulty_dir="A",
        actual_departure_ts=datetime(2026, 6, 1, 10),
        actual_arrival_ts=datetime(2026, 6, 1, 11),
        period_start_utc=datetime(2026, 6, 1, 10),
        period_end_utc=datetime(2026, 6, 1, 11),
        sequence_ts=datetime(2026, 6, 1, 10),
        export_ready=True,
    )
    insert_row(con, "core_loco_timeline", entry)
    insert_row(con, "core_loco_timeline", exit_row)
    con.execute("update core_loco_timeline set export_blocking=false")
    phase6c.build_central_de_usage_segments(con, "RUN_TEST")
    row = con.execute("select segment_start_utc, segment_end_utc, movement_count from core_usage_assignment_segments").fetchone()
    assert row == (datetime(2026, 6, 1, 9), datetime(2026, 6, 1, 10), 2)


@pytest.mark.integration
def test_relevant_gap_breaks_central_usage_segment(con):
    create_core_timeline(con)
    ensure_phase6c_columns(con)
    insert_row(con, "core_loco_timeline", movement(1, origin_name="A", destination_name="B"))
    insert_row(con, "core_loco_timeline", gap(1, minutes=60, origin_name="B", destination_name="C"))
    insert_row(
        con,
        "core_loco_timeline",
        movement(
            2,
            period_start_utc=datetime(2026, 6, 1, 12),
            period_end_utc=datetime(2026, 6, 1, 13),
            actual_departure_ts=datetime(2026, 6, 1, 12),
            actual_arrival_ts=datetime(2026, 6, 1, 13),
            sequence_ts=datetime(2026, 6, 1, 12),
            origin_name="C",
            destination_name="D",
        ),
    )
    con.execute("update core_loco_timeline set export_blocking=false where row_type='MOVEMENT'")
    phase6c.build_central_de_usage_segments(con, "RUN_TEST")
    assert con.execute("select count(*) from core_usage_assignment_segments").fetchone()[0] == 2

@pytest.mark.rules
def test_phase6c_adds_symmetric_r012_dummy_from_transportdetail(con):
    create_core_timeline(con)
    create_findings_shell(con)
    create_rule_catalog_shell(con)
    create_dq_metadata(con)
    con.execute("create table cfg_excluded_cancelled_transports (transport_number varchar, transport_status varchar)")
    con.execute("""
        create table raw_transportdetail (
            TransportNumber varchar, OriginCountryISO varchar, DestinationCountryISO varchar,
            ActualDeparture varchar, FirstLocomotiveNo varchar, MovementType varchar
        )
    """)
    con.execute("insert into raw_transportdetail values ('TR-DUMMY-TD','DE','DE','2026-06-01T10:00:00','00000000000-0','Train movement')")
    phase6c._insert_r012_transportdetail_dummy_findings(con, "RUN_TEST")
    assert con.execute("select rule_id, transport_number from dq_findings").fetchone() == ("R012", "TR-DUMMY-TD")
