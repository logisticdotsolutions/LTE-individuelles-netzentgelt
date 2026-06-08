from __future__ import annotations

# NETZENTGELT_RULE_ENGINE_HARDENING_PHASE6C_V1_20260608

import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "02_duckdb" / "netzentgelt.duckdb"
EXP_DIR = ROOT / "data" / "03_exports"
BACKUP_ROOT = ROOT / ".netzentgelt_hotfix_backups"


def run(cmd: list[str]) -> None:
    completed = subprocess.run(cmd, cwd=str(ROOT), text=True)
    if completed.returncode != 0:
        raise RuntimeError("Befehl fehlgeschlagen: " + " ".join(cmd))


def main() -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = BACKUP_ROOT / f"rule_engine_hardening_phase6c_runtime_{stamp}"
    backup.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        target = backup / "data" / "02_duckdb" / DB_PATH.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(DB_PATH, target)
    if EXP_DIR.exists():
        shutil.copytree(EXP_DIR, backup / "data" / "03_exports", dirs_exist_ok=True)
    print(f"Runtime-Backup erstellt: {backup.relative_to(ROOT)}")
    try:
        run([sys.executable, str(ROOT / "scripts" / "run_all.py")])
        run([sys.executable, str(ROOT / "scripts" / "verify_rule_engine_hardening_phase6c.py")])
    except Exception:
        print("FEHLER: Pipeline oder Verifikation fehlgeschlagen. Letzten Datenstand wiederherstellen ...")
        backup_db = backup / "data" / "02_duckdb" / DB_PATH.name
        if backup_db.exists():
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup_db, DB_PATH)
        backup_exports = backup / "data" / "03_exports"
        if backup_exports.exists():
            if EXP_DIR.exists(): shutil.rmtree(EXP_DIR)
            shutil.copytree(backup_exports, EXP_DIR)
        raise
    print("OK: Pipeline und Phase-6C-Verifikation erfolgreich.")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FEHLER: {exc}")
        raise SystemExit(1)
