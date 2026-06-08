from __future__ import annotations

from pathlib import Path
import sys
import duckdb

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "02_duckdb" / "netzentgelt.duckdb"


def table_exists(con, table_name: str) -> bool:
    return con.execute(
        "select count(*) from information_schema.tables where lower(table_name)=lower(?)",
        [table_name],
    ).fetchone()[0] > 0


def main() -> int:
    if not DB_PATH.exists():
        print(f"FEHLER: Produktive DuckDB fehlt: {DB_PATH}")
        return 1
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        for table in ["core_loco_timeline", "core_loco_day_coverage", "dq_export_gate"]:
            if not table_exists(con, table):
                print(f"FEHLER: Tabelle fehlt nach Pipeline-Lauf: {table}")
                return 1
        false_positives = con.execute(
            """
            with movement_intervals as (
                select
                    row_number() over () as overlap_row_no,
                    loco_no,
                    period_start_utc,
                    period_end_utc
                from core_loco_timeline
                where row_type = 'MOVEMENT'
                  and report_scope = 'IN_REPORT'
                  and nullif(trim(loco_no), '') is not null
                  and period_start_utc is not null
                  and period_end_utc is not null
                  and period_end_utc > period_start_utc
            ),
            actual_overlap_days as (
                select distinct
                    a.loco_no,
                    cast(greatest(a.period_start_utc, b.period_start_utc) as date) as coverage_date
                from movement_intervals a
                join movement_intervals b
                  on b.loco_no = a.loco_no
                 and b.overlap_row_no > a.overlap_row_no
                 and a.period_start_utc < b.period_end_utc
                 and b.period_start_utc < a.period_end_utc
            )
            select c.loco_no, c.coverage_date, c.overlap_minutes
            from core_loco_day_coverage c
            left join actual_overlap_days a
              on a.loco_no = c.loco_no
             and a.coverage_date = c.coverage_date
            where coalesce(c.overlap_minutes, 0) > 0
              and a.loco_no is null
            order by c.coverage_date, c.loco_no
            """
        ).fetchall()
        if false_positives:
            print("FEHLER: Quality Gate enthält weiterhin Overlap-Fehlalarme ohne echte Zeitüberschneidung:")
            for row in false_positives[:30]:
                print("  ", row)
            return 1
        overlap_days = con.execute(
            "select count(*) from core_loco_day_coverage where coalesce(overlap_minutes, 0) > 0"
        ).fetchone()[0]
        print("OK: Keine Overlap-Fehlalarme ohne echte Zeitüberschneidung gefunden.")
        print(f"OK: Verbleibende Lok-Tage mit tatsächlicher Überschneidung: {int(overlap_days)}")
        print("HINWEIS: Andere Sperrgründe wie nicht exportfähige Bewegungen bleiben bewusst unverändert.")
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
