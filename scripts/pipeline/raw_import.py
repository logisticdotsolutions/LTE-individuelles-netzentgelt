"""Raw-DuckDB-Layer fuer den Netzentgelt-MVP.

Dieser Schritt importiert nur die CSV-/Datalake-Rohdaten in eine eigene DuckDB.
Die fachliche Berechnung laeuft danach separat aus diesem stabilen Raw-Snapshot.
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb

from .context import PipelineContext


def _ensure_scripts_dir_on_path() -> None:
    scripts_dir = Path(__file__).resolve().parents[1]
    scripts_dir_text = str(scripts_dir)

    if scripts_dir_text not in sys.path:
        sys.path.insert(0, scripts_dir_text)


def _remove_if_exists(path: Path) -> None:
    if path.exists():
        path.unlink()


def run_raw_import(ctx: PipelineContext) -> str:
    """Rohdaten frisch nach `netzentgelt_raw.duckdb` importieren."""
    ctx.ensure_directories()
    _ensure_scripts_dir_on_path()

    from run_all import import_csvs

    _remove_if_exists(ctx.raw_db_path)
    _remove_if_exists(Path(str(ctx.raw_db_path) + ".wal"))

    con = None
    try:
        print(f"Erzeuge Raw-Datenbank: {ctx.raw_db_path}")
        con = duckdb.connect(str(ctx.raw_db_path))
        run_id, imported_tables = import_csvs(con)
        con.close()
        con = None
        return f"RAW_IMPORT abgeschlossen. Raw-Run: {run_id}. Tabellen: {len(imported_tables)}"
    except Exception:
        if con is not None:
            con.close()
        _remove_if_exists(ctx.raw_db_path)
        _remove_if_exists(Path(str(ctx.raw_db_path) + ".wal"))
        raise
