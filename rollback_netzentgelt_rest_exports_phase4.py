from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LAST_BACKUP_FILE = ROOT / ".rest_export_phase4_last_backup.txt"
MODULE_TARGET = ROOT / "scripts" / "rest_export_module.py"


def main() -> int:
    if not LAST_BACKUP_FILE.exists():
        raise RuntimeError("Kein Phase-4-Backupverweis gefunden.")

    backup_dir = Path(LAST_BACKUP_FILE.read_text(encoding="utf-8").strip())
    if not backup_dir.exists():
        raise RuntimeError(f"Backup-Ordner fehlt: {backup_dir}")

    restored: list[str] = []
    for source in backup_dir.rglob("*"):
        if source.is_file():
            destination = ROOT / source.relative_to(backup_dir)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            restored.append(str(destination.relative_to(ROOT)))

    backup_module = backup_dir / MODULE_TARGET.relative_to(ROOT)
    if not backup_module.exists() and MODULE_TARGET.exists():
        MODULE_TARGET.unlink()
        restored.append(f"{MODULE_TARGET.relative_to(ROOT)} entfernt")

    print("Rollback erfolgreich:")
    for value in restored:
        print(f"- {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
