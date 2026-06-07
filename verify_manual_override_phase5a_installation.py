#!/usr/bin/env python3
"""Lokale Installations- und optionale Laufzeitprüfung für Phase 5A."""
from __future__ import annotations

import argparse
import ast
import csv
from pathlib import Path
import sys

try:
    import duckdb
except Exception:
    duckdb = None

PHASE_ID = "NETZENTGELT_MANUAL_OVERRIDE_PHASE5A_V1_20260607"
REQUIRED_FILES = [
    "scripts/run_all.py",
    "app/app.py",
    "scripts/manual_override_module.py",
    "scripts/manual_override_ui_module.py",
]
REQUIRED_DB_TABLES = [
    "cfg_manual_overrides",
    "cfg_manual_overrides_effective",
    "dq_manual_override_conflicts",
    "audit_manual_override_application",
]
REQUIRED_EXPORTS = [
    "cfg_manual_overrides.csv",
    "cfg_manual_overrides_effective.csv",
    "dq_manual_override_conflicts.csv",
    "audit_manual_override_application.csv",
]
REQUIRED_OVERRIDE_COLUMNS = [
    "override_id",
    "active_flag",
    "override_type",
    "transport_number",
    "target_loco_no",
    "target_actual_departure_utc",
    "target_actual_arrival_utc",
    "target_source_table",
    "target_source_row_id",
    "override_value",
    "classification_code",
    "comment",
    "created_by",
    "created_at_utc",
    "updated_at_utc",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--require-db-tables", action="store_true")
    return parser.parse_args()


def fail(message: str) -> None:
    print(f"FEHLER: {message}", file=sys.stderr)
    raise SystemExit(1)


def syntax_check(path: Path) -> None:
    try:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except Exception as exc:
        fail(f"Syntaxprüfung fehlgeschlagen: {path}: {exc}")


def line_ending_label(path: Path) -> str:
    raw = path.read_bytes()
    return "CRLF" if b"\r\n" in raw else "LF"


def verify_mapping_schema(project_root: Path) -> None:
    path = project_root / "data" / "01_mapping" / "manual_overrides.csv"
    if not path.exists():
        print("HINWEIS: manual_overrides.csv wird beim ersten App- oder Pipeline-Lauf automatisch angelegt.")
        return
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, delimiter=";")
        header = next(reader, [])
    missing = [column for column in REQUIRED_OVERRIDE_COLUMNS if column not in header]
    if missing:
        fail("manual_overrides.csv enthält nicht alle erwarteten Spalten: " + ", ".join(missing))
    print("Override-CSV-Schema geprüft.")


def verify_db(project_root: Path, require: bool) -> None:
    db_path = project_root / "data" / "02_duckdb" / "netzentgelt.duckdb"
    if not db_path.exists():
        if require:
            fail(f"DuckDB fehlt: {db_path}")
        print("HINWEIS: DuckDB-Laufzeitprüfung übersprungen; produktive DB fehlt noch.")
        return
    if duckdb is None:
        fail("duckdb-Paket fehlt in der verwendeten Python-Umgebung.")
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        existing = {
            row[0].lower()
            for row in con.execute("select table_name from information_schema.tables").fetchall()
        }
        missing = [name for name in REQUIRED_DB_TABLES if name.lower() not in existing]
        if missing:
            if require:
                fail("Phase-5A-Tabellen fehlen in DuckDB: " + ", ".join(missing))
            print("HINWEIS: DuckDB wurde noch nicht mit Phase 5A neu aufgebaut.")
            return
        conflicts = int(con.execute("select count(*) from dq_manual_override_conflicts").fetchone()[0])
        if conflicts:
            fail(f"Aktive Override-Konflikte vorhanden: {conflicts}")
        active = int(con.execute("select count(*) from cfg_manual_overrides_effective").fetchone()[0])
        audit = int(con.execute("select count(*) from audit_manual_override_application").fetchone()[0])
        print(f"DuckDB geprüft: aktive Overrides={active}, Audit-Anwendungen={audit}, Konflikte=0.")
    finally:
        con.close()


def verify_exports(project_root: Path, require: bool) -> None:
    export_dir = project_root / "data" / "03_exports"
    missing = [name for name in REQUIRED_EXPORTS if not (export_dir / name).exists()]
    if missing and require:
        fail("Phase-5A-Audit-CSV-Dateien fehlen: " + ", ".join(missing))
    if missing:
        print("HINWEIS: Audit-CSV-Dateien entstehen beim nächsten Pipeline-Lauf.")
    else:
        print("Phase-5A-Audit-CSV-Dateien geprüft.")


def main() -> None:
    args = parse_args()
    root = Path(args.project_root).resolve()
    for relative in REQUIRED_FILES:
        path = root / relative
        if not path.exists():
            fail(f"Datei fehlt: {relative}")
        syntax_check(path)
        print(f"Syntax OK: {relative} ({line_ending_label(path)})")

    run_all = (root / "scripts" / "run_all.py").read_text(encoding="utf-8")
    app = (root / "app" / "app.py").read_text(encoding="utf-8")
    for needle in [
        PHASE_ID,
        "import_manual_overrides(con)",
        "apply_raw_manual_overrides(con, run_id)",
        "apply_staging_manual_overrides(con, run_id)",
        "audit_manual_override_application.csv",
    ]:
        if needle not in run_all:
            fail(f"run_all.py enthält erwartete Phase-5A-Stelle nicht: {needle}")
    for needle in [PHASE_ID, "render_manual_override_cockpit", '"3. Fall bearbeiten"']:
        if needle not in app:
            fail(f"app.py enthält erwartete Phase-5A-Stelle nicht: {needle}")

    verify_mapping_schema(root)
    verify_db(root, args.require_db_tables)
    verify_exports(root, args.require_db_tables)
    print("PHASE 5A VERIFICATION OK")


if __name__ == "__main__":
    main()
