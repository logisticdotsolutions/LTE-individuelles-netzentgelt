from __future__ import annotations

"""Sicherer Pipeline-Lauf mit Runtime-Backup, Verifikation und Daten-Rollback."""

import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_DIR = ROOT / "data" / "02_duckdb"
DB_PATH = DB_DIR / "netzentgelt.duckdb"
EXPORT_DIR = ROOT / "data" / "03_exports"
BACKUP_ROOT = ROOT / ".netzentgelt_hotfix_backups"
RUN_ALL = ROOT / "scripts" / "run_all.py"
VERIFY = ROOT / "scripts" / "verify_rule_engine_hardening_phase6d.py"


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def backup_runtime() -> Path:
    target = BACKUP_ROOT / f"runtime_rule_engine_phase6d_{stamp()}"
    target.mkdir(parents=True, exist_ok=False)
    if DB_PATH.exists():
        shutil.copy2(DB_PATH, target / "netzentgelt.duckdb")
    if EXPORT_DIR.exists():
        shutil.copytree(EXPORT_DIR, target / "03_exports")
    (target / "README.txt").write_text(
        "Runtime-Backup vor Phase-6D-Pipeline. Bei Fehler wird automatisch wiederhergestellt.\n",
        encoding="utf-8",
    )
    return target


def restore_runtime(backup: Path) -> None:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    backup_db = backup / "netzentgelt.duckdb"
    if backup_db.exists():
        shutil.copy2(backup_db, DB_PATH)
    if EXPORT_DIR.exists():
        shutil.rmtree(EXPORT_DIR)
    backup_exports = backup / "03_exports"
    if backup_exports.exists():
        shutil.copytree(backup_exports, EXPORT_DIR)


def run(command: list[str]) -> None:
    result = subprocess.run(command, cwd=ROOT, text=True)
    if result.returncode != 0:
        raise RuntimeError("Befehl fehlgeschlagen: " + " ".join(command))


def main() -> int:
    backup = backup_runtime()
    print(f"Runtime-Backup: {backup}")
    try:
        run([sys.executable, str(RUN_ALL)])
        run([sys.executable, str(VERIFY)])
    except Exception:
        print("FEHLER: Phase-6D-Pipeline fehlgeschlagen. Vorheriger Datenstand wird wiederhergestellt.")
        restore_runtime(backup)
        raise
    print("OK: Pipeline und Phase-6D-Verifikation erfolgreich.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
