from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB = ROOT / "data" / "02_duckdb" / "netzentgelt.duckdb"
EXPORTS = ROOT / "data" / "03_exports"
BACKUP_ROOT = ROOT / ".netzentgelt_hotfix_backups"
LATEST = BACKUP_ROOT / "qg_actual_overlap_runtime_latest.txt"


def backup_runtime() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = BACKUP_ROOT / f"qg_actual_overlap_runtime_{stamp}"
    dest.mkdir(parents=True, exist_ok=True)
    if DB.exists():
        (dest / "data" / "02_duckdb").mkdir(parents=True, exist_ok=True)
        shutil.copy2(DB, dest / "data" / "02_duckdb" / DB.name)
    if EXPORTS.exists():
        shutil.copytree(EXPORTS, dest / "data" / "03_exports")
    (dest / "manifest.json").write_text(json.dumps({"created_at_utc": datetime.now(timezone.utc).isoformat(), "db_existed": DB.exists(), "exports_existed": EXPORTS.exists()}, indent=2), encoding="utf-8")
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    LATEST.write_text(str(dest.relative_to(ROOT)).replace("\\", "/"), encoding="utf-8")
    return dest


def restore_runtime(dest: Path) -> None:
    manifest = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
    if DB.exists():
        DB.unlink()
    backup_db = dest / "data" / "02_duckdb" / DB.name
    if manifest.get("db_existed") and backup_db.exists():
        DB.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup_db, DB)
    if EXPORTS.exists():
        shutil.rmtree(EXPORTS)
    backup_exports = dest / "data" / "03_exports"
    if manifest.get("exports_existed") and backup_exports.exists():
        shutil.copytree(backup_exports, EXPORTS)


def run(script: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(script)], cwd=str(ROOT), capture_output=True, text=True)


def main() -> int:
    backup = backup_runtime()
    print(f"OK: Runtime-Backup erstellt: {backup.relative_to(ROOT)}")
    pipeline = run(ROOT / "scripts" / "run_all.py")
    print(pipeline.stdout)
    if pipeline.returncode != 0:
        print(pipeline.stderr)
        restore_runtime(backup)
        print("FEHLER: Pipeline fehlgeschlagen. Vorheriger Runtime-Stand wurde automatisch wiederhergestellt.")
        return 1
    verify = run(ROOT / "verify_quality_gate_overlap_data.py")
    print(verify.stdout)
    if verify.returncode != 0:
        print(verify.stderr)
        restore_runtime(backup)
        print("FEHLER: Fachliche Verifikation fehlgeschlagen. Vorheriger Runtime-Stand wurde automatisch wiederhergestellt.")
        return 1
    print("OK: Pipeline und fachliche Overlap-Verifikation erfolgreich.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
