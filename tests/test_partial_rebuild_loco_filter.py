"""
TDD-Tests fuer loco_filter in Pipeline-Funktionen (Partial-Rebuild)
====================================================================

Diese Tests definieren das erwartete Verhalten BEVOR die Implementierung
existiert (klassisches TDD). Sie schuetzen die kritische Invariante:

    Nicht-betroffene Loks bleiben unveraendert.
    Betroffene Loks werden neu berechnet.
    loco_filter=None entspricht dem bisherigen Vollneubau.

Solange loco_filter noch nicht implementiert ist, schlagen diese Tests
mit TypeError ("unexpected keyword argument 'loco_filter'") fehl.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import error_rules
import quality_gate_module as qg
from tests.support.builders import (
    FINDING_COLUMNS,
    create_table,
    create_core_timeline,
    create_dq_metadata,
    ensure_phase6c_columns,
    insert_row,
    movement,
    prepare_base,
)


# ---------------------------------------------------------------------------
# Fixture-Helfer
# ---------------------------------------------------------------------------

def _loco(loco_no: str, row_id: int = 1, **kw) -> dict:
    return movement(row_id=row_id, loco_no=loco_no, transport_number=f"TR-{loco_no}-{row_id}", **kw)


def _findings_for(con, loco_no: str) -> list[tuple]:
    return con.execute(
        "select rule_id, severity from dq_findings where loco_no = ? order by rule_id",
        [loco_no],
    ).fetchall()


def _gate_rows_for(con, loco_no: str) -> list[tuple]:
    return con.execute(
        "select gate_status from dq_export_gate where loco_no = ? order by coverage_date",
        [loco_no],
    ).fetchall()


def _build_minimal_segments(con, loco_no: str) -> None:
    """Minimale Segment-Tabellen fuer einen build_quality_gate_tables-Test."""
    if not _table_exists_local(con, "core_usage_assignment_segments"):
        con.execute("""
            create or replace table core_usage_assignment_segments (
                run_id varchar, loco_no varchar, usage_segment_no bigint,
                usage_segment_id varchar, tfze_or_tens varchar, performing_ru varchar,
                segment_start_utc timestamp, segment_end_utc timestamp,
                first_actual_departure_utc timestamp, last_actual_arrival_utc timestamp,
                movement_count bigint, export_ready_movement_rows bigint,
                export_blocking_movement_rows bigint, user_vens varchar,
                holder_name varchar, holder_market_partner_id varchar
            )
        """)
    if not _table_exists_local(con, "core_usage_assignment_segment_movements"):
        con.execute("""
            create or replace table core_usage_assignment_segment_movements (
                run_id varchar, loco_no varchar, usage_segment_no bigint,
                usage_segment_id varchar, tfze_or_tens varchar, performing_ru varchar,
                de_period_start_utc timestamp, de_period_end_utc timestamp,
                actual_departure_ts timestamp, actual_arrival_ts timestamp,
                source_table varchar, source_row_id bigint,
                export_ready boolean, export_blocking boolean,
                user_vens varchar, holder_name varchar, holder_market_partner_id varchar
            )
        """)
    con.execute("""
        insert into core_usage_assignment_segments values (
            'RUN_TEST', ?, 1, ?, ?, 'RU GmbH',
            '2026-06-01 10:00'::timestamp, '2026-06-01 11:00'::timestamp,
            '2026-06-01 10:00'::timestamp, '2026-06-01 11:00'::timestamp,
            1, 1, 0, 'RU GmbH', 'Holder GmbH', null
        )
    """, [loco_no, f"SEG-{loco_no}-1", loco_no])
    con.execute("""
        insert into core_usage_assignment_segment_movements
            (run_id, loco_no, usage_segment_no, usage_segment_id, tfze_or_tens,
             performing_ru, de_period_start_utc, de_period_end_utc,
             actual_departure_ts, actual_arrival_ts, source_table, source_row_id,
             export_ready, export_blocking)
        values (
            'RUN_TEST', ?, 1, ?, ?, 'RU GmbH',
            '2026-06-01 10:00'::timestamp, '2026-06-01 11:00'::timestamp,
            '2026-06-01 10:00'::timestamp, '2026-06-01 11:00'::timestamp,
            'raw_locomotivemovement', 1, true, false
        )
    """, [loco_no, f"SEG-{loco_no}-1", loco_no])


def _table_exists_local(con, name: str) -> bool:
    return con.execute(
        "select count(*) from information_schema.tables where lower(table_name) = lower(?)",
        [name],
    ).fetchone()[0] > 0


def _loco_with_error(loco_no: str, row_id: int = 1) -> dict:
    """Bewegung ohne sequence_ts nach der ersten (R001 ERROR) — erzeugt immer ein Finding."""
    return _loco(loco_no, row_id=row_id, movement_sequence_no=2, sequence_ts=None)


def _con_with_three_locos() -> duckdb.DuckDBPyConnection:
    """In-Memory-DB mit core_loco_timeline fuer L1, L2, L3 (je ein Finding per Lok)."""
    con = duckdb.connect(":memory:")
    prepare_base(con, rows=[
        _loco_with_error("L1", row_id=1),
        _loco_with_error("L2", row_id=2),
        _loco_with_error("L3", row_id=3),
    ])
    return con


# ---------------------------------------------------------------------------
# build_findings — loco_filter
# ---------------------------------------------------------------------------

class TestBuildFindingsLocoFilter:

    def test_loco_filter_none_behaves_like_full_rebuild(self):
        """loco_filter=None muss dasselbe Ergebnis liefern wie der bisherige Aufruf ohne Parameter."""
        con_ref = _con_with_three_locos()
        con_filtered = _con_with_three_locos()

        error_rules.build_findings(con_ref, "RUN_TEST")
        error_rules.build_findings(con_filtered, "RUN_TEST", loco_filter=None)

        for loco in ("L1", "L2", "L3"):
            assert _findings_for(con_ref, loco) == _findings_for(con_filtered, loco), (
                f"loco_filter=None weicht vom Referenz-Rebuild fuer Lok {loco} ab."
            )

    def test_unaffected_locos_are_not_touched(self):
        """Nach partial rebuild fuer L1 duerfen L2 und L3 unveraendert bleiben."""
        con = _con_with_three_locos()
        error_rules.build_findings(con, "RUN_TEST")

        # Snapshot von L2 und L3
        l2_before = _findings_for(con, "L2")
        l3_before = _findings_for(con, "L3")

        # Partial rebuild nur fuer L1
        error_rules.build_findings(con, "RUN_TEST", loco_filter=frozenset({"L1"}))

        assert _findings_for(con, "L2") == l2_before, "L2-Findings wurden unveraendert erwartet."
        assert _findings_for(con, "L3") == l3_before, "L3-Findings wurden unveraendert erwartet."

    def test_affected_loco_is_rebuilt(self):
        """Nach partial rebuild fuer L1 hat L1 weiterhin Findings (wurde neu berechnet)."""
        con = _con_with_three_locos()
        error_rules.build_findings(con, "RUN_TEST")

        # Loeschung simuliert veralteten Zustand fuer L1
        con.execute("delete from dq_findings where loco_no = 'L1'")
        assert _findings_for(con, "L1") == [], "Setup: L1 sollte keine Findings haben."

        error_rules.build_findings(con, "RUN_TEST", loco_filter=frozenset({"L1"}))

        # L1 wurde wieder berechnet
        assert len(_findings_for(con, "L1")) > 0, "L1 hat nach partial rebuild keine Findings."

    def test_partial_filter_matches_full_rebuild_for_affected_loco(self):
        """Partial rebuild fuer L1 muss fachlich identisches Ergebnis wie Vollneubau liefern."""
        con_full = _con_with_three_locos()
        error_rules.build_findings(con_full, "RUN_TEST")
        l1_full = _findings_for(con_full, "L1")

        con_partial = _con_with_three_locos()
        error_rules.build_findings(con_partial, "RUN_TEST")
        # Partial rebuild — Ergebnis fuer L1 muss identisch sein
        error_rules.build_findings(con_partial, "RUN_TEST", loco_filter=frozenset({"L1"}))
        l1_partial = _findings_for(con_partial, "L1")

        assert l1_full == l1_partial, (
            f"Partial rebuild fuer L1 weicht vom Vollneubau ab.\n"
            f"Vollneubau: {l1_full}\nPartial:    {l1_partial}"
        )

    def test_empty_filter_rebuilds_nothing(self):
        """loco_filter={} (leere Menge) darf keine Findings veraendern."""
        con = _con_with_three_locos()
        error_rules.build_findings(con, "RUN_TEST")

        before = {
            loco: _findings_for(con, loco)
            for loco in ("L1", "L2", "L3")
        }

        error_rules.build_findings(con, "RUN_TEST", loco_filter=frozenset())

        for loco in ("L1", "L2", "L3"):
            assert _findings_for(con, loco) == before[loco], (
                f"Leerer loco_filter hat Findings fuer {loco} veraendert."
            )


# ---------------------------------------------------------------------------
# build_quality_gate_tables — loco_filter
# ---------------------------------------------------------------------------

def _con_with_gate_setup(locos: list[str]) -> duckdb.DuckDBPyConnection:
    """DB mit core_loco_timeline, dq_findings, dq_run_metadata, core_usage_assignment_segments."""
    con = duckdb.connect(":memory:")
    rows = [_loco_with_error(lo, row_id=i + 1) for i, lo in enumerate(locos)]
    prepare_base(con, rows=rows)
    ensure_phase6c_columns(con)
    error_rules.build_findings(con, "RUN_TEST")
    for lo in locos:
        _build_minimal_segments(con, lo)
    return con


class TestBuildQualityGateLocoFilter:

    def test_loco_filter_none_behaves_like_full_rebuild(self):
        """loco_filter=None muss dasselbe Ergebnis wie der bisherige Vollneubau liefern."""
        con_ref = _con_with_gate_setup(["L1", "L2", "L3"])
        con_filtered = _con_with_gate_setup(["L1", "L2", "L3"])

        qg.build_quality_gate_tables(con_ref, "RUN_TEST")
        qg.build_quality_gate_tables(con_filtered, "RUN_TEST", loco_filter=None)

        for loco in ("L1", "L2", "L3"):
            assert _gate_rows_for(con_ref, loco) == _gate_rows_for(con_filtered, loco), (
                f"loco_filter=None weicht vom Referenz-Rebuild fuer Lok {loco} ab."
            )

    def test_unaffected_locos_are_not_touched(self):
        """Nach partial rebuild fuer L1 duerfen L2 und L3 im Gate unveraendert bleiben."""
        con = _con_with_gate_setup(["L1", "L2", "L3"])
        qg.build_quality_gate_tables(con, "RUN_TEST")

        l2_before = _gate_rows_for(con, "L2")
        l3_before = _gate_rows_for(con, "L3")

        qg.build_quality_gate_tables(con, "RUN_TEST", loco_filter=frozenset({"L1"}))

        assert _gate_rows_for(con, "L2") == l2_before, "L2-Gate wurde unveraendert erwartet."
        assert _gate_rows_for(con, "L3") == l3_before, "L3-Gate wurde unveraendert erwartet."

    def test_affected_loco_is_rebuilt_in_gate(self):
        """Nach partial rebuild fuer L1 hat L1 einen Gate-Eintrag (wurde neu berechnet)."""
        con = _con_with_gate_setup(["L1", "L2", "L3"])
        qg.build_quality_gate_tables(con, "RUN_TEST")

        con.execute("delete from dq_export_gate where loco_no = 'L1'")
        con.execute("delete from core_loco_day_coverage where loco_no = 'L1'")
        assert _gate_rows_for(con, "L1") == [], "Setup: L1 sollte keinen Gate-Eintrag haben."

        qg.build_quality_gate_tables(con, "RUN_TEST", loco_filter=frozenset({"L1"}))

        assert len(_gate_rows_for(con, "L1")) > 0, "L1 hat nach partial rebuild keinen Gate-Eintrag."

    def test_partial_filter_matches_full_rebuild_for_affected_loco(self):
        """Partial rebuild fuer L1 muss fachlich identischen Gate-Status wie Vollneubau liefern."""
        con_full = _con_with_gate_setup(["L1", "L2", "L3"])
        qg.build_quality_gate_tables(con_full, "RUN_TEST")
        l1_full = _gate_rows_for(con_full, "L1")

        con_partial = _con_with_gate_setup(["L1", "L2", "L3"])
        qg.build_quality_gate_tables(con_partial, "RUN_TEST")
        qg.build_quality_gate_tables(con_partial, "RUN_TEST", loco_filter=frozenset({"L1"}))
        l1_partial = _gate_rows_for(con_partial, "L1")

        assert l1_full == l1_partial, (
            f"Partial rebuild fuer L1-Gate weicht vom Vollneubau ab.\n"
            f"Vollneubau: {l1_full}\nPartial:    {l1_partial}"
        )


# ---------------------------------------------------------------------------
# Invariante: global_export_blockers immer neu berechnet
# ---------------------------------------------------------------------------

class TestGlobalBlockersAlwaysRebuilt:

    def test_global_blockers_table_exists_after_partial_rebuild(self):
        """
        dq_global_export_blockers ist eine Aggregation ueber ALLE Loks.
        Sie muss auch bei partial rebuild neu berechnet werden.
        """
        con = _con_with_gate_setup(["L1", "L2"])
        qg.build_quality_gate_tables(con, "RUN_TEST", loco_filter=frozenset({"L1"}))
        assert _table_exists_local(con, "dq_global_export_blockers"), (
            "dq_global_export_blockers fehlt nach partial rebuild. "
            "Globale Blocker muessen immer neu berechnet werden."
        )
