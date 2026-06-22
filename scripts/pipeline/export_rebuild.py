"""Schneller Export-Rebuild auf Basis der vorhandenen Tages-DuckDB.

Dieser Schritt ist fuer Faelle gedacht, in denen Exporttabellen oder CSV-Dateien
neu erzeugt werden muessen, ohne Rohdatenimport, Staging, Core-Zeitachse,
Findings oder Quality-Gate neu aufzubauen.
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb

from .context import PipelineContext
from .csv_outputs import export_all_csv_outputs


def _ensure_scripts_dir_on_path() -> None:
    """Imports bestehender Legacy-Module aus dem scripts-Verzeichnis erlauben."""
    scripts_dir = Path(__file__).resolve().parents[1]
    scripts_dir_text = str(scripts_dir)

    if scripts_dir_text not in sys.path:
        sys.path.insert(0, scripts_dir_text)


def run_export_rebuild(ctx: PipelineContext) -> str:
    """Exporttabellen und CSV-Dateien aus vorhandener Produktiv-DuckDB neu erzeugen."""
    ctx.ensure_directories()

    if not ctx.db_path.exists():
        raise FileNotFoundError(
            f"Produktive DuckDB nicht gefunden: {ctx.db_path}. "
            "Zuerst FULL_IMPORT_REBUILD bzw. scripts/run_all.py ausfuehren."
        )

    _ensure_scripts_dir_on_path()

    from export_module import build_export_tables
    from quality_gate_module import refresh_reconciliation_table

    con = None

    try:
        print(f"Oeffne vorhandene Tages-Datenbank: {ctx.db_path}")
        con = duckdb.connect(str(ctx.db_path))

        print("Erzeuge Exporttabellen neu...")
        build_export_tables(con)

        print("Aktualisiere Reconciliation-Tabelle...")
        refresh_reconciliation_table(con, ctx.run_id)

        print("Schreibe CSV-Ausgaben neu...")
        written_files = export_all_csv_outputs(con, ctx.export_dir)

        return f"EXPORT_REBUILD abgeschlossen. CSV-Dateien geschrieben: {len(written_files)}"

    finally:
        if con is not None:
            con.close()
