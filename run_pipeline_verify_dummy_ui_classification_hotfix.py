from __future__ import annotations

import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB = ROOT / "data" / "02_duckdb" / "netzentgelt.duckdb"
EXP = ROOT / "data" / "03_exports"
BACKUP_ROOT = ROOT / ".dummy_ui_classification_runtime_backups"


def run(args: list[str]) -> None:
    result = subprocess.run(args, cwd=str(ROOT), text=True)
    if result.returncode != 0:
        raise RuntimeError("Befehl fehlgeschlagen: " + " ".join(args))


def restore(backup: Path) -> None:
    db_backup = backup / "netzentgelt.duckdb"
    exp_backup = backup / "03_exports"
    if db_backup.exists():
        DB.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(db_backup, DB)
    if EXP.exists():
        shutil.rmtree(EXP)
    if exp_backup.exists():
        shutil.copytree(exp_backup, EXP)


def main() -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_%f")
    backup = BACKUP_ROOT / stamp
    backup.mkdir(parents=True, exist_ok=True)
    if DB.exists():
        shutil.copy2(DB, backup / "netzentgelt.duckdb")
    if EXP.exists():
        shutil.copytree(EXP, backup / "03_exports")
    try:
        run([sys.executable, str(ROOT / "scripts" / "run_all.py")])
        run([sys.executable, str(ROOT / "scripts" / "verify_dummy_locomotive_hardening.py")])
        run([sys.executable, str(ROOT / "scripts" / "verify_dummy_locomotive_ui_classification.py")])
    except Exception as error:
        print(f"FEHLER: {error}")
        print("Stelle letzten DuckDB-/Exportstand wieder her ...")
        restore(backup)
        return 1
    print("OK: Pipeline und Dummy-UI-Klassifikation erfolgreich.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
