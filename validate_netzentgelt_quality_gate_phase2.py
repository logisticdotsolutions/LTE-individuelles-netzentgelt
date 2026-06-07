from __future__ import annotations

from pathlib import Path
import sys

import duckdb

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "02_duckdb" / "netzentgelt.duckdb"

REQUIRED_TABLES = [
    "core_loco_day_coverage",
    "dq_export_gate",
    "dq_export_gate_ru",
    "dq_global_export_blockers",
    "export_excluded_rows",
    "dq_reconciliation",
    "dq_operational_kpis",
]


def table_exists(con, table_name: str) -> bool:
    return (
        con.execute(
            """
            select count(*)
            from information_schema.tables
            where lower(table_name) = lower(?)
            """,
            [table_name],
        ).fetchone()[0]
        > 0
    )


def main() -> int:
    if not DB_PATH.exists():
        print(f"FEHLER: Produktive DuckDB fehlt: {DB_PATH}")
        return 2

    con = duckdb.connect(str(DB_PATH), read_only=True)

    try:
        missing = [name for name in REQUIRED_TABLES if not table_exists(con, name)]

        if missing:
            print("FEHLER: Phase-2-Tabellen fehlen:")
            for name in missing:
                print(f"- {name}")
            return 3

        gate = con.execute(
            """
            select
                count(*) filter (where gate_status = 'READY') as ready_days,
                count(*) filter (where gate_status = 'WARNING') as warning_days,
                count(*) filter (where gate_status = 'BLOCKED') as blocked_days
            from dq_export_gate
            """
        ).fetchone()

        reconciliation = con.execute(
            """
            select
                run_id,
                total_coverage_pct,
                unresolved_gap_minutes,
                overlap_minutes,
                global_export_blockers,
                excluded_export_rows
            from dq_reconciliation
            limit 1
            """
        ).fetchone()

        print("")
        print("=" * 80)
        print("Netzentgelt Phase 2 - Validierung erfolgreich")
        print("=" * 80)
        print(f"Lok-Tage READY:   {gate[0]}")
        print(f"Lok-Tage WARNING: {gate[1]}")
        print(f"Lok-Tage BLOCKED: {gate[2]}")

        if reconciliation:
            print(f"Run-ID:                  {reconciliation[0]}")
            print(f"Deckungsquote:           {reconciliation[1]} %")
            print(f"Ungeklärte GAP-Minuten:  {reconciliation[2]}")
            print(f"Overlap-Minuten:         {reconciliation[3]}")
            print(f"Globale Export-Blocker:  {reconciliation[4]}")
            print(f"Ausgeschlossene Zeilen:  {reconciliation[5]}")

        print("")
        print("Hinweis: BLOCKED- und WARNING-Werte sind fachliche Ergebnisse.")
        print("Sie bedeuten nicht, dass die Pipeline technisch fehlgeschlagen ist.")
        print("=" * 80)
        return 0

    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
