#!/usr/bin/env python3
"""Sichert oder restauriert DuckDB und Exportordner vor einem produktiven Phase-5A-Lauf."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
from datetime import datetime, timezone


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def snapshot(root: Path) -> None:
    backup_root = root / ".netzentgelt_runtime_backups"
    target = backup_root / ("manual_override_phase5a_" + stamp())
    target.mkdir(parents=True, exist_ok=False)
    db = root / "data" / "02_duckdb" / "netzentgelt.duckdb"
    exports = root / "data" / "03_exports"
    manifest = {"created_at_utc": stamp(), "db_existed": db.exists(), "exports_existed": exports.exists()}
    if db.exists():
        (target / "data" / "02_duckdb").mkdir(parents=True, exist_ok=True)
        shutil.copy2(db, target / "data" / "02_duckdb" / db.name)
    if exports.exists():
        shutil.copytree(exports, target / "data" / "03_exports")
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (backup_root / "LATEST_MANUAL_OVERRIDE_PHASE5A_RUNTIME.txt").write_text(str(target), encoding="utf-8")
    print(f"Runtime-Backup erstellt: {target}")


def rollback(root: Path) -> None:
    pointer = root / ".netzentgelt_runtime_backups" / "LATEST_MANUAL_OVERRIDE_PHASE5A_RUNTIME.txt"
    if not pointer.exists():
        print("Kein Runtime-Backup vorhanden; Runtime-Rollback übersprungen.")
        return
    source = Path(pointer.read_text(encoding="utf-8").strip())
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    db = root / "data" / "02_duckdb" / "netzentgelt.duckdb"
    exports = root / "data" / "03_exports"
    if db.exists():
        db.unlink()
    if manifest["db_existed"]:
        db.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / "data" / "02_duckdb" / db.name, db)
    if exports.exists():
        shutil.rmtree(exports)
    if manifest["exports_existed"]:
        shutil.copytree(source / "data" / "03_exports", exports)
    else:
        exports.mkdir(parents=True, exist_ok=True)
    print(f"Runtime-Rollback erfolgreich aus: {source}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--snapshot", action="store_true")
    parser.add_argument("--rollback", action="store_true")
    args = parser.parse_args()
    if bool(args.snapshot) == bool(args.rollback):
        raise SystemExit("Genau eine Aktion angeben: --snapshot oder --rollback")
    root = Path(args.project_root).resolve()
    snapshot(root) if args.snapshot else rollback(root)


if __name__ == "__main__":
    main()
