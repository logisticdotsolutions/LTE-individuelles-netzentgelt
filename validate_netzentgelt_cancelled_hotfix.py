from __future__ import annotations

import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MARKER = "# NETZENTGELT_CANCELLED_FILTER_HOTFIX_V1_1_20260607"
TARGETS = [
    Path("scripts/run_all.py"),
    Path("scripts/error_rules.py"),
    Path("scripts/export_module.py"),
    Path("app/app.py"),
]


def main() -> int:
    for relative in TARGETS:
        absolute = ROOT / relative
        if not absolute.exists():
            raise RuntimeError(f"Datei fehlt: {relative}")
        text = absolute.read_text(encoding="utf-8")
        if MARKER not in text:
            raise RuntimeError(f"Hotfix-Marker fehlt in: {relative}")
        py_compile.compile(str(absolute), doraise=True)

    db_path = ROOT / "data" / "02_duckdb" / "netzentgelt.duckdb"
    if db_path.exists():
        try:
            import duckdb
            con = duckdb.connect(str(db_path), read_only=True)
            exists = con.execute("""
                select count(*)
                from information_schema.tables
                where lower(table_name) = 'audit_excluded_cancelled_transports'
            """).fetchone()[0]
            if exists:
                rows = con.execute("""
                    select coalesce(sum(affected_rows), 0)
                    from audit_excluded_cancelled_transports
                """).fetchone()[0]
                print(
                    "Audit-Tabelle vorhanden: "
                    f"{rows} stornierte Rohdatenzeilen fachlich ausgeschlossen."
                )
            else:
                print("Hinweis: Audit-Tabelle noch nicht vorhanden. Bitte vollständige Pipeline einmal ausführen.")
            con.close()
        except Exception as error:
            print(f"Hinweis: DuckDB-Prüfung nicht möglich: {error}")

    print("Validierung erfolgreich.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
