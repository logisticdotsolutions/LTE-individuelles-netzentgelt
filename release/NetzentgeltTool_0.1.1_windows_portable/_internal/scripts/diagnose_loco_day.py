from __future__ import annotations

"""
Gezielte Diagnose fuer einen Lok-Kalendertag im Netzentgelt-MVP.

Das Skript veraendert keine Daten. Es liest ausschliesslich die produktive DuckDB
und zeigt Gate, Timeline, GAPs, Nutzungssegmente sowie Findings fuer eine Lok und
einen Kalendertag. Damit lassen sich scheinbar unsichtbare GAP-Sperren auditierbar
nachvollziehen.
"""

import argparse
from datetime import date, datetime, timedelta
from pathlib import Path
import sys

import duckdb


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / "data" / "02_duckdb" / "netzentgelt.duckdb"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Lok-Tag aus der produktiven Netzentgelt-DuckDB diagnostizieren."
    )
    parser.add_argument("--loco", required=True, help="Loknummer, zum Beispiel 91806193740-8")
    parser.add_argument("--date", required=True, help="Kalendertag im Format YYYY-MM-DD")
    parser.add_argument(
        "--db",
        default=str(DEFAULT_DB_PATH),
        help="Optionaler Pfad zur DuckDB. Standard: data/02_duckdb/netzentgelt.duckdb",
    )
    return parser.parse_args()


def parse_day(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise SystemExit("FEHLER: --date muss im Format YYYY-MM-DD angegeben werden.") from error


def table_exists(con: duckdb.DuckDBPyConnection, table_name: str) -> bool:
    return bool(
        con.execute(
            """
            select count(*) > 0
            from information_schema.tables
            where lower(table_name) = lower(?)
            """,
            [table_name],
        ).fetchone()[0]
    )


def print_query(
    con: duckdb.DuckDBPyConnection,
    *,
    title: str,
    table_name: str,
    sql: str,
    parameters: list[object],
) -> None:
    print("")
    print("=" * 100)
    print(title)
    print("=" * 100)
    if not table_exists(con, table_name):
        print(f"INFO: Tabelle {table_name} ist nicht vorhanden.")
        return

    result = con.execute(sql, parameters).fetchdf()
    if result.empty:
        print("INFO: Keine passenden Zeilen gefunden.")
        return

    print(result.to_string(index=False))


def main() -> int:
    args = parse_args()
    selected_day = parse_day(args.date)
    day_start = datetime.combine(selected_day, datetime.min.time())
    day_end = day_start + timedelta(days=1)
    context_start = day_start - timedelta(days=1)
    context_end = day_end + timedelta(days=1)
    db_path = Path(args.db).resolve()

    if not db_path.exists():
        print(f"FEHLER: DuckDB nicht gefunden: {db_path}", file=sys.stderr)
        return 2

    print("Netzentgelt Lok-Tag-Diagnose")
    print(f"DuckDB: {db_path}")
    print(f"Lok:    {args.loco}")
    print(f"Tag:    {selected_day.isoformat()} [00:00, Folgetag 00:00)")

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        print_query(
            con,
            title="1. DQ EXPORT GATE JE LOK UND TAG",
            table_name="dq_export_gate",
            sql="""
                select *
                from dq_export_gate
                where loco_no = ?
                  and coverage_date = ?::date
            """,
            parameters=[args.loco, selected_day.isoformat()],
        )

        print_query(
            con,
            title="2. DQ EXPORT GATE JE LOK, TAG UND PERFORMING RU",
            table_name="dq_export_gate_ru",
            sql="""
                select *
                from dq_export_gate_ru
                where loco_no = ?
                  and coverage_date = ?::date
                order by performing_ru
            """,
            parameters=[args.loco, selected_day.isoformat()],
        )

        print_query(
            con,
            title="3. GAP-ZEILEN MIT INTERVALLUEBERSCHNEIDUNG ZUM AUSGEWAEHLTEN TAG",
            table_name="core_loco_timeline",
            sql="""
                select
                    row_type,
                    loco_no,
                    transport_number,
                    performing_ru,
                    period_start_utc,
                    period_end_utc,
                    gap_from_utc,
                    gap_to_utc,
                    gap_duration_minutes,
                    gap_relevant_de,
                    gap_time_basis_safe,
                    gap_context_class,
                    origin_name,
                    destination_name,
                    dq_severity,
                    dq_message,
                    source_table,
                    source_row_id
                from core_loco_timeline
                where loco_no = ?
                  and row_type = 'GAP'
                  and coalesce(gap_from_utc, period_start_utc) < ?::timestamp
                  and coalesce(gap_to_utc, period_end_utc) > ?::timestamp
                order by coalesce(gap_from_utc, period_start_utc), source_row_id
            """,
            parameters=[args.loco, day_end, day_start],
        )

        print_query(
            con,
            title="4. TIMELINE-KONTEXT: BEWEGUNGEN UND GAPs VOM VORTAG BIS ZUM FOLGETAG",
            table_name="core_loco_timeline",
            sql="""
                select
                    row_type,
                    loco_no,
                    transport_number,
                    performing_ru,
                    actual_departure_ts,
                    actual_arrival_ts,
                    period_start_utc,
                    period_end_utc,
                    gap_duration_minutes,
                    gap_relevant_de,
                    report_scope,
                    de_event_label,
                    origin_name,
                    destination_name,
                    dq_severity,
                    dq_message,
                    source_table,
                    source_row_id
                from core_loco_timeline
                where loco_no = ?
                  and coalesce(period_end_utc, period_start_utc, sequence_ts) >= ?::timestamp
                  and coalesce(period_start_utc, period_end_utc, sequence_ts) < ?::timestamp
                order by coalesce(period_start_utc, sequence_ts, period_end_utc), sort_sequence
            """,
            parameters=[args.loco, context_start, context_end],
        )

        print_query(
            con,
            title="5. ZENTRALE DE-NUTZUNGSSEGMENTE MIT INTERVALLUEBERSCHNEIDUNG",
            table_name="core_usage_assignment_segments",
            sql="""
                select *
                from core_usage_assignment_segments
                where loco_no = ?
                  and segment_start_utc < ?::timestamp
                  and segment_end_utc > ?::timestamp
                order by segment_start_utc, usage_segment_no
            """,
            parameters=[args.loco, day_end, day_start],
        )

        print_query(
            con,
            title="6. FINDINGS MIT BEZUG ZUM AUSGEWAEHLTEN TAG",
            table_name="dq_findings",
            sql="""
                select
                    rule_id,
                    severity,
                    row_type,
                    loco_no,
                    transport_number,
                    performing_ru,
                    period_start_utc,
                    period_end_utc,
                    message,
                    suggested_action,
                    status,
                    source_table,
                    source_row_id
                from dq_findings
                where loco_no = ?
                  and (
                        cast(coalesce(period_start_utc, period_end_utc) as date) = ?::date
                     or (
                            period_start_utc is not null
                        and period_end_utc is not null
                        and period_start_utc < ?::timestamp
                        and period_end_utc > ?::timestamp
                     )
                  )
                order by severity, rule_id, period_start_utc
            """,
            parameters=[args.loco, selected_day.isoformat(), day_end, day_start],
        )

        print_query(
            con,
            title="7. R016 GAP-ONLY-TAGESFINDINGS FUER DIE LOK",
            table_name="dq_findings",
            sql="""
                select *
                from dq_findings
                where loco_no = ?
                  and rule_id = 'R016'
                order by period_start_utc
            """,
            parameters=[args.loco],
        )

        print_query(
            con,
            title="8. POTENZIELLE KALTE ABSTELLUNGEN MIT INTERVALLUEBERSCHNEIDUNG",
            table_name="core_loco_stand_candidates",
            sql="""
                select *
                from core_loco_stand_candidates
                where loco_no = ?
                  and stand_from_utc < ?::timestamp
                  and stand_to_utc > ?::timestamp
                order by stand_from_utc
            """,
            parameters=[args.loco, day_end, day_start],
        )

    finally:
        con.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
