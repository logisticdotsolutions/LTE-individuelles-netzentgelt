#!/usr/bin/env python3
"""Fachlicher Smoke-Test der Phase-5B-Vorschlags-Engine mit isolierter DuckDB."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tempfile

import duckdb
import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=".")
    return parser.parse_args()


def install_import_path(project_root: Path) -> None:
    scripts = project_root / "scripts"
    if not scripts.exists():
        # Paketinterner Test vor Installation.
        scripts = Path(__file__).resolve().parent / "payload"
    sys.path.insert(0, str(scripts))


def main() -> int:
    args = parse_args()
    project_root = Path(args.project_root).resolve()
    install_import_path(project_root)

    from manual_override_suggestion_module import (  # noqa: PLC0415
        build_suggestion_table,
        suggestion_for_case,
    )

    with tempfile.TemporaryDirectory(prefix="phase5b_logic_") as tmp:
        db_path = Path(tmp) / "phase5b.duckdb"
        con = duckdb.connect(str(db_path))
        con.execute(
            """
            create table core_loco_timeline (
                row_type varchar,
                loco_no varchar,
                transport_number varchar,
                period_start_utc timestamp,
                period_end_utc timestamp,
                sequence_ts timestamp,
                actual_departure_ts timestamp,
                actual_arrival_ts timestamp,
                performing_ru varchar,
                clean_dir varchar,
                faulty_dir varchar,
                report_scope varchar,
                origin_name varchar,
                destination_name varchar,
                source_table varchar,
                source_row_id bigint,
                gap_relevant_de boolean,
                gap_duration_minutes bigint
            )
            """
        )
        timeline_rows = [
            # PerformingRU-Vorschlag: beide Nachbarn stimmen überein.
            ("MOVEMENT", "L1", "T_PRE", "2026-06-01 08:00", "2026-06-01 09:00", "2026-06-01 08:07", "2026-06-01 08:00", "2026-06-01 09:00", "LTE NL", "E", "", "IN_REPORT", "A", "B", "raw_locomotivemovement", 1, False, None),
            ("MOVEMENT", "L1", "T_MISSING_RU", "2026-06-01 10:00", "2026-06-01 11:00", None, "2026-06-01 10:00", "2026-06-01 11:00", None, "", "", "IN_REPORT", "B", "C", "raw_locomotivemovement", 2, False, None),
            ("MOVEMENT", "L1", "T_NEXT", "2026-06-01 12:00", "2026-06-01 13:00", "2026-06-01 12:00", "2026-06-01 12:00", "2026-06-01 13:00", "LTE NL", "A", "", "IN_REPORT", "C", "D", "raw_locomotivemovement", 3, False, None),
            # Konflikt: beide Nachbarn unterschiedlich, daher keine Vorauswahl.
            ("MOVEMENT", "L_CONFLICT", "TC_PRE", "2026-06-01 08:00", "2026-06-01 09:00", "2026-06-01 08:00", "2026-06-01 08:00", "2026-06-01 09:00", "LTE DE", "", "", "IN_REPORT", "A", "B", "raw_locomotivemovement", 10, False, None),
            ("MOVEMENT", "L_CONFLICT", "TC_MISSING", "2026-06-01 10:00", "2026-06-01 11:00", None, "2026-06-01 10:00", "2026-06-01 11:00", None, "", "", "IN_REPORT", "B", "C", "raw_locomotivemovement", 11, False, None),
            ("MOVEMENT", "L_CONFLICT", "TC_NEXT", "2026-06-01 12:00", "2026-06-01 13:00", "2026-06-01 12:00", "2026-06-01 12:00", "2026-06-01 13:00", "LTE NL", "", "", "IN_REPORT", "C", "D", "raw_locomotivemovement", 12, False, None),
            # Kalte Abstellung: gleicher Ort, Standzeit > 8h.
            ("MOVEMENT", "L2", "T_ST1", "2026-06-01 06:00", "2026-06-01 07:00", "2026-06-01 06:00", "2026-06-01 06:00", "2026-06-01 07:00", "LTE DE", "", "", "IN_REPORT", "X", "STATION", "raw_locomotivemovement", 4, False, None),
            ("MOVEMENT", "L2", "T_ST2", "2026-06-01 18:00", "2026-06-01 19:00", "2026-06-01 18:00", "2026-06-01 18:00", "2026-06-01 19:00", "LTE DE", "", "", "IN_REPORT", "STATION", "Y", "raw_locomotivemovement", 5, False, None),
            # Gebrochene Ortskette.
            ("GAP", "L3", "T_GAP", "2026-06-01 09:00", "2026-06-01 20:00", None, None, None, None, "", "", "GAP", "OLD", "NEW", "raw_locomotivemovement", 6, True, 660),
        ]
        con.executemany(
            "insert into core_loco_timeline values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            timeline_rows,
        )
        con.execute("create table raw_transportdetail (TransportNumber varchar, FirstLocomotiveNo varchar)")
        con.execute("insert into raw_transportdetail values ('T_R012', 'L9')")
        con.execute("create table raw_locomotivemovement (TransportNumber varchar, LocomotiveNo varchar)")
        con.execute("insert into raw_locomotivemovement values ('T_R012', 'L9')")
        before = con.execute("select count(*) from core_loco_timeline").fetchone()[0]
        con.close()

        findings = pd.DataFrame(
            [
                {"rule_id": "R009", "transport_number": "T_MISSING_RU", "loco_no": "L1", "period_start_utc": "2026-06-01 10:00:00", "period_end_utc": "2026-06-01 11:00:00", "source_table": "raw_locomotivemovement", "source_row_id": "2"},
                {"rule_id": "R009", "transport_number": "TC_MISSING", "loco_no": "L_CONFLICT", "period_start_utc": "2026-06-01 10:00:00", "period_end_utc": "2026-06-01 11:00:00", "source_table": "raw_locomotivemovement", "source_row_id": "11"},
                {"rule_id": "R012", "transport_number": "T_R012", "loco_no": "", "period_start_utc": "2026-06-01 10:00:00", "period_end_utc": "", "source_table": "raw_transportdetail", "source_row_id": "7"},
                {"rule_id": "R001", "transport_number": "T_PRE", "loco_no": "L1", "period_start_utc": "2026-06-01 08:00:00", "period_end_utc": "2026-06-01 09:00:00", "source_table": "raw_locomotivemovement", "source_row_id": "1"},
            ]
        )
        timeline = pd.DataFrame(
            timeline_rows,
            columns=[
                "row_type", "loco_no", "transport_number", "period_start_utc", "period_end_utc", "sequence_ts",
                "actual_departure_ts", "actual_arrival_ts", "performing_ru", "clean_dir", "faulty_dir", "report_scope",
                "origin_name", "destination_name", "source_table", "source_row_id", "gap_relevant_de", "gap_duration_minutes",
            ],
        )

        suggestions = build_suggestion_table(db_path=db_path, findings=findings, timeline=timeline)

        def has(**expected: str) -> bool:
            mask = pd.Series(True, index=suggestions.index)
            for key, value in expected.items():
                mask &= suggestions[key].fillna("").astype(str).eq(value)
            return bool(mask.any())

        assert has(suggestion_type="PERFORMING_RU_FROM_BOTH_NEIGHBOURS", suggested_value="LTE NL", confidence="HIGH")
        assert has(suggestion_type="PERFORMING_RU_CONFLICT", suggested_value="", confidence="LOW")
        assert has(suggestion_type="LOCO_NO_FROM_TRANSPORT", suggested_value="L9", confidence="HIGH")
        assert has(suggestion_type="POSSIBLE_COLD_STAND_SAME_LOCATION", classification_code="COLD_STAND", confidence="MEDIUM")
        assert has(suggestion_type="BROKEN_LOCATION_CHAIN", classification_code="MISSING_MOVEMENT", confidence="MEDIUM")
        assert has(suggestion_type="BORDER_QUARTER_HOUR_REVIEW", suggested_value="2026-06-01T08:00:00", confidence="LOW")
        assert has(suggestion_type="SEQUENCE_TS_FROM_DIRECTION", suggested_value="2026-06-01T08:00:00", confidence="MEDIUM")

        single = suggestion_for_case(
            db_path=db_path,
            override_type="SET_PERFORMING_RU",
            transport_number="T_MISSING_RU",
            loco_no="L1",
            period_start_utc="2026-06-01 10:00:00",
        )
        assert single.suggested_value == "LTE NL" and single.confidence == "HIGH"

        # Engine darf keinerlei Rohdaten verändern.
        con = duckdb.connect(str(db_path), read_only=True)
        after = con.execute("select count(*) from core_loco_timeline").fetchone()[0]
        con.close()
        assert before == after

    print("PHASE 5B LOGIC VERIFY OK")
    print("- PerformingRU: HIGH-Vorschlag aus übereinstimmenden Nachbarbewegungen")
    print("- PerformingRU-Konflikt: LOW ohne Vorauswahl")
    print("- Loknummer: HIGH-Vorschlag aus beiden Transportquellen")
    print("- Mögliche kalte Abstellung: MEDIUM, nur Dokumentationsvorschlag")
    print("- Gebrochene Ortskette: MEDIUM, fehlende Bewegung vermutet")
    print("- Grenzereignis: LOW-Viertelstunden-Prüfvorschlag")
    print("- Engine ist read-only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
