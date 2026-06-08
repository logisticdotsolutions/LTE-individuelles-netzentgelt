from __future__ import annotations

"""Verifikation der produktiven Phase-6D-DuckDB nach einem vollständigen Lauf."""

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "02_duckdb" / "netzentgelt.duckdb"


def table_exists(con, table_name: str) -> bool:
    return con.execute(
        "select count(*) from information_schema.tables where lower(table_name)=lower(?)",
        [table_name],
    ).fetchone()[0] > 0


def columns(con, table_name: str) -> set[str]:
    return {row[0].lower() for row in con.execute(f'describe "{table_name}"').fetchall()}


def verify(db_path: Path) -> None:
    import duckdb

    if not db_path.exists():
        raise RuntimeError(f"DuckDB fehlt: {db_path}")
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        required = [
            "dq_findings",
            "dq_export_gate",
            "dq_export_gate_ru",
            "core_loco_day_coverage",
            "dq_phase6d_exact_overlap_days",
            "dq_rule_engine_hardening_phase6d_audit",
            "core_loco_stand_candidates",
            "dq_phase6c_gap_context_review",
            "dq_phase6c_uncertain_gaps",
        ]
        missing = [name for name in required if not table_exists(con, name)]
        if missing:
            raise RuntimeError("Fehlende Phase-6D-Tabellen: " + ", ".join(missing))

        for table_name in ["core_loco_day_coverage", "dq_export_gate", "dq_export_gate_ru"]:
            missing_columns = {"exact_overlap_seconds", "exact_overlap_minutes"} - columns(con, table_name)
            if missing_columns:
                raise RuntimeError(
                    f"{table_name}: fehlende Spalten: {', '.join(sorted(missing_columns))}"
                )

        hidden_gap_only = int(con.execute("""
            select count(*)
            from dq_export_gate g
            where g.gate_status = 'BLOCKED'
              and coalesce(g.assigned_minutes, 0) = 0
              and coalesce(g.unresolved_gap_minutes, 0) > 0
              and coalesce(g.error_findings, 0) = 0
              and coalesce(g.manual_review_findings, 0) = 0
              and coalesce(g.overlap_minutes, 0) = 0
              and coalesce(g.long_gap_rows, 0) = 0
        """).fetchone()[0])

        missing_exact = int(con.execute("""
            select count(*)
            from dq_export_gate
            where coalesce(overlap_minutes, 0) > 0
              and exact_overlap_minutes is null
        """).fetchone()[0])

        r016 = int(con.execute("select count(*) from dq_findings where rule_id='R016'").fetchone()[0])
        exact_days = int(con.execute("select count(*) from dq_phase6d_exact_overlap_days").fetchone()[0])
        audit_rows = int(con.execute("select count(*) from dq_rule_engine_hardening_phase6d_audit").fetchone()[0])
        stands = int(con.execute("select count(*) from core_loco_stand_candidates").fetchone()[0])
        border = int(con.execute("select count(*) from dq_phase6c_gap_context_review").fetchone()[0])
        uncertain = int(con.execute("select count(*) from dq_phase6c_uncertain_gaps").fetchone()[0])

        print("Phase-6D-Verifikation:")
        print(f"  GAP-only-Lok-Tage ohne sichtbares R016: {hidden_gap_only}")
        print(f"  R016-Prueffaelle: {r016}")
        print(f"  Overlap-Tage ohne exakte Dauer: {missing_exact}")
        print(f"  Lok-Tage mit exakter Overlap-Dauer: {exact_days}")
        print(f"  Potenzielle kalte Abstellungen: {stands}")
        print(f"  Grenzkontext zur Sichtung: {border}")
        print(f"  Unsichere GAPs: {uncertain}")
        print(f"  Phase-6D-Auditzeilen: {audit_rows}")

        failures = []
        if hidden_gap_only:
            failures.append(f"{hidden_gap_only} GAP-only-Lok-Tage ohne sichtbares R016")
        if missing_exact:
            failures.append(f"{missing_exact} Overlap-Tage ohne exakte Dauer")
        if audit_rows <= 0:
            failures.append("Phase-6D-Audit ist leer")
        if failures:
            raise RuntimeError("Phase-6D-Verifikation fehlgeschlagen: " + " | ".join(failures))
        print("OK: Phase-6D-Verifikation erfolgreich.")
    finally:
        con.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    verify(args.db)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
