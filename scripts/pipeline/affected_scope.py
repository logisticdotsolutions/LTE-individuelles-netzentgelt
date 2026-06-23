"""Ermittlung des von Korrekturen betroffenen Lok-Scope fuer partiellen Rebuild."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import duckdb


def _loco_hashes_from_con(con, table_name: str) -> dict[str, str]:
    """Pro loco_no einen MD5-Hash ueber alle Override-Zeilen berechnen.

    Liefert '__GLOBAL__' fuer Zeilen ohne target_loco_no.
    """
    try:
        rows = con.execute(
            f"select * from {table_name} order by coalesce(override_id, '')"
        ).fetchall()
    except Exception:
        return {}

    desc_rows = con.execute(f"describe {table_name}").fetchall()
    col_names = [r[0].lower() for r in desc_rows]

    loco_idx = col_names.index("target_loco_no") if "target_loco_no" in col_names else None
    if loco_idx is None:
        return {}

    by_loco: dict[str, list] = {}
    for row in rows:
        loco = str(row[loco_idx] or "").strip() or "__GLOBAL__"
        by_loco.setdefault(loco, []).append(row)

    return {
        loco: hashlib.md5(str(loco_rows).encode()).hexdigest()
        for loco, loco_rows in by_loco.items()
    }


def _loco_hashes_from_csv(csv_path: Path) -> dict[str, str] | None:
    """Wie _loco_hashes_from_con, aber direkt aus einer CSV-Datei."""
    try:
        con = duckdb.connect(":memory:")
        try:
            con.execute(
                """
                create table _overrides as
                select * from read_csv_auto(
                    ?,
                    delim=';',
                    header=true,
                    all_varchar=true,
                    ignore_errors=false,
                    union_by_name=true
                )
                """,
                [str(csv_path)],
            )
            return _loco_hashes_from_con(con, "_overrides")
        finally:
            con.close()
    except Exception:
        return None


def get_affected_loco_nos(
    prod_db_path: Path,
    overrides_csv_path: Path,
) -> frozenset[str] | None:
    """Vergleicht Override-Zustand in der Prod-DB mit der neuen CSV.

    Gibt None zurueck, wenn ein vollstaendiger Rebuild erforderlich ist
    (Prod-DB fehlt, Tabelle fehlt, Lesefehler).
    Gibt frozenset() zurueck, wenn keine Aenderungen vorliegen.
    Gibt frozenset({loco_no, ...}) fuer betroffene Loknummern zurueck.
    """
    if not prod_db_path.exists():
        return None

    if not overrides_csv_path.exists():
        return frozenset()

    try:
        prod_con = duckdb.connect(str(prod_db_path), read_only=True)
        try:
            exists = prod_con.execute(
                "select count(*) from information_schema.tables "
                "where lower(table_name) = 'cfg_manual_overrides'"
            ).fetchone()[0]
            if not exists:
                return None
            old_hashes = _loco_hashes_from_con(prod_con, "cfg_manual_overrides")
        finally:
            prod_con.close()
    except Exception:
        return None

    new_hashes = _loco_hashes_from_csv(overrides_csv_path)
    if new_hashes is None:
        return None

    all_keys = set(old_hashes) | set(new_hashes)
    affected: set[str] = set()
    for key in all_keys:
        if old_hashes.get(key) != new_hashes.get(key):
            if key == "__GLOBAL__":
                return None  # Nicht-loko-spezifische Overrides geaendert → Vollneubau
            affected.add(key)

    return frozenset(affected)
