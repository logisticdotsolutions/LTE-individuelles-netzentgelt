from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKUP_ROOT = ROOT / ".netzentgelt_hotfix_backups"
LATEST_FILE = BACKUP_ROOT / "repository_cleanup_phase5e_latest.txt"

PATTERNS = [
    ".netzentgelt_hotfix_backups/**",
    ".phase5c_latest_backup.txt",
    "01_DRY_RUN_MANUAL_OVERRIDE_PHASE5B.bat",
    "02_APPLY_MANUAL_OVERRIDE_PHASE5B.bat",
    "03_VERIFY_MANUAL_OVERRIDE_PHASE5B.bat",
    "04_RUN_PHASE5B_LOGIC_TESTS.bat",
    "05_ROLLBACK_MANUAL_OVERRIDE_PHASE5B.bat",
    "06_PACKAGE_SELFTEST_MANUAL_OVERRIDE_PHASE5B.bat",
    "01_DRY_RUN_OPERATIONAL_DAY_FILTER_PHASE5C.bat",
    "02_APPLY_OPERATIONAL_DAY_FILTER_PHASE5C.bat",
    "03_VERIFY_OPERATIONAL_DAY_FILTER_PHASE5C.bat",
    "04_RUN_OPERATIONAL_DAY_FILTER_PHASE5C_TESTS.bat",
    "05_ROLLBACK_OPERATIONAL_DAY_FILTER_PHASE5C.bat",
    "01_DRY_RUN_MANUAL_OVERRIDE_PHASE5D.bat",
    "02_APPLY_MANUAL_OVERRIDE_PHASE5D.bat",
    "03_VERIFY_MANUAL_OVERRIDE_PHASE5D.bat",
    "04_RUN_MANUAL_OVERRIDE_PHASE5D_TESTS.bat",
    "05_ROLLBACK_MANUAL_OVERRIDE_PHASE5D.bat",
    "README_MANUAL_OVERRIDE_PHASE5B.md",
    "README_PHASE5C.md",
    "README_PHASE5D.md",
    "TEST_REPORT_MANUAL_OVERRIDE_PHASE5B.md",
    "apply_netzentgelt_manual_override_phase5b.py",
    "apply_operational_day_filter_phase5c.py",
    "apply_netzentgelt_phase5d.py",
    "payload/**",
    "data/04_logs/**",
    "test_phase5d_logic.py",
    "package_selftest.py",
    "verify_manual_override_phase5b_installation.py",
    "verify_manual_override_phase5b_logic.py",
    "tests/fixtures/manual_override_module_phase5a.py",
    "tests/fixtures/manual_override_ui_module_phase5a.py",
    "tests/test_installer_phase5c.py",
]

# Diese Dateien gehören zum aktuellen Übergabepaket und bleiben lokal erhalten,
# bis Christoph den Commit geprüft hat. Sie sind über .gitignore ausgeblendet.
PHASE5E_LOCAL_FILES = {
    "01_DRY_RUN_CONTROLLER_UX_PHASE5E.bat",
    "02_APPLY_CONTROLLER_UX_PHASE5E.bat",
    "03_VERIFY_CONTROLLER_UX_PHASE5E.bat",
    "04_RUN_CONTROLLER_UX_PHASE5E_TESTS.bat",
    "05_ROLLBACK_CONTROLLER_UX_PHASE5E.bat",
    "06_CLEANUP_REPOSITORY_PHASE5E.bat",
    "07_ROLLBACK_REPOSITORY_CLEANUP_PHASE5E.bat",
    "apply_netzentgelt_phase5e.py",
    "cleanup_repository_phase5e.py",
    "test_phase5e_logic.py",
    "README_PHASE5E.md",
}

class CleanupError(RuntimeError):
    pass

def _run_git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True, text=True)
    if result.returncode != 0:
        raise CleanupError(result.stderr.strip() or "Git-Befehl fehlgeschlagen.")
    return result.stdout

def _tracked_files() -> list[str]:
    return [line.strip() for line in _run_git("ls-files").splitlines() if line.strip()]

def _matches(path: str) -> bool:
    if path in PHASE5E_LOCAL_FILES:
        return False
    return any(fnmatch(path, pattern) for pattern in PATTERNS)

def candidates() -> list[str]:
    return sorted(path for path in _tracked_files() if _matches(path))

def dry_run() -> int:
    files = candidates()
    if not files:
        print("Keine alten Installationsartefakte gefunden.")
        return 0
    print("Folgende alte Installationsartefakte würden entfernt:")
    for path in files:
        print(" -", path)
    print(f"Gesamt: {len(files)} Datei(en).")
    return 0

def apply() -> int:
    files = candidates()
    if not files:
        print("Keine alten Installationsartefakte gefunden.")
        return 0
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = BACKUP_ROOT / f"repository_cleanup_phase5e_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)
    manifest = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "files": files}
    for relative in files:
        src = ROOT / relative
        if src.exists() and src.is_file():
            dst = backup_dir / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    (backup_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    LATEST_FILE.parent.mkdir(parents=True, exist_ok=True)
    LATEST_FILE.write_text(str(backup_dir.relative_to(ROOT)), encoding="utf-8")
    for relative in files:
        path = ROOT / relative
        if path.exists() and path.is_file():
            path.unlink()
    # Leere Verzeichnisse defensiv entfernen.
    for directory in sorted({(ROOT / item).parent for item in files}, key=lambda p: len(p.parts), reverse=True):
        try:
            directory.rmdir()
        except OSError:
            pass
    print(f"Repository-Bereinigung erfolgreich. Entfernt: {len(files)} Datei(en). Backup: {backup_dir}")
    return 0

def rollback() -> int:
    if not LATEST_FILE.exists():
        raise CleanupError("Kein Repository-Cleanup-Backup gefunden.")
    backup_dir = ROOT / LATEST_FILE.read_text(encoding="utf-8").strip()
    manifest = json.loads((backup_dir / "manifest.json").read_text(encoding="utf-8"))
    restored = 0
    for relative in manifest["files"]:
        src = backup_dir / relative
        dst = ROOT / relative
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            restored += 1
    print(f"Repository-Cleanup-Rollback erfolgreich. Wiederhergestellt: {restored} Datei(en).")
    return 0

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["dry-run", "apply", "rollback"])
    args = parser.parse_args()
    try:
        return {"dry-run": dry_run, "apply": apply, "rollback": rollback}[args.mode]()
    except CleanupError as exc:
        print(f"FEHLER: {exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
