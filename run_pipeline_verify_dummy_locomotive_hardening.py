from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
DB = ROOT / "data" / "02_duckdb" / "netzentgelt.duckdb"
EXP = ROOT / "data" / "03_exports"


def main() -> int:
    backup = Path(tempfile.mkdtemp(prefix="netzentgelt_dummy_runtime_backup_"))
    db_backup = backup / "netzentgelt.duckdb"
    exp_backup = backup / "03_exports"
    try:
        if DB.exists():
            shutil.copy2(DB, db_backup)
        if EXP.exists():
            shutil.copytree(EXP, exp_backup)

        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "run_all.py")],
            cwd=str(ROOT),
        )
        if result.returncode != 0:
            raise RuntimeError("run_all.py fehlgeschlagen")

        verify = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "verify_dummy_locomotive_hardening.py")],
            cwd=str(ROOT),
        )
        if verify.returncode != 0:
            raise RuntimeError("Dummy-Lok-Verifikation fehlgeschlagen")

        print("OK: Pipeline und Dummy-Lok-Verifikation erfolgreich.")
        return 0
    except Exception as exc:
        print(f"FEHLER: {exc}")
        print("Stelle letzten DuckDB-/Exportstand wieder her ...")
        if DB.exists():
            DB.unlink()
        if db_backup.exists():
            shutil.copy2(db_backup, DB)
        if EXP.exists():
            shutil.rmtree(EXP)
        if exp_backup.exists():
            shutil.copytree(exp_backup, EXP)
        return 1
    finally:
        shutil.rmtree(backup, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
