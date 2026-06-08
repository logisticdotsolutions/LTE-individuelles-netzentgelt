from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB = ROOT / "data" / "02_duckdb" / "netzentgelt.duckdb"
EXPORTS = ROOT / "data" / "03_exports"
BACKUP_ROOT = ROOT / ".netzentgelt_hotfix_backups"
LATEST = BACKUP_ROOT / "qg_actual_overlap_runtime_latest.txt"


def main() -> int:
    if not LATEST.exists():
        print("HINWEIS: Kein Runtime-Backup vorhanden. Nur Code-Rollback wird benötigt.")
        return 0
    backup = ROOT / LATEST.read_text(encoding="utf-8").strip()
    manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    if DB.exists():
        DB.unlink()
    backup_db = backup / "data" / "02_duckdb" / DB.name
    if manifest.get("db_existed") and backup_db.exists():
        DB.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup_db, DB)
    if EXPORTS.exists():
        shutil.rmtree(EXPORTS)
    backup_exports = backup / "data" / "03_exports"
    if manifest.get("exports_existed") and backup_exports.exists():
        shutil.copytree(backup_exports, EXPORTS)
    print(f"OK: Runtime-Stand wiederhergestellt aus: {backup.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
