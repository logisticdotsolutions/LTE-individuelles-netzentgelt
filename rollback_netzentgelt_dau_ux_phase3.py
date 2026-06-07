from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LAST_BACKUP_FILE = ROOT / ".dau_ux_phase3_last_backup.txt"
NEW_MODULE_TARGET = ROOT / "scripts" / "operator_ui_module.py"


def main() -> int:
    if not LAST_BACKUP_FILE.exists():
        raise RuntimeError("Kein Phase-3-Backupverweis gefunden.")

    backup_dir = Path(LAST_BACKUP_FILE.read_text(encoding="utf-8").strip())
    if not backup_dir.exists():
        raise RuntimeError(f"Backup-Ordner fehlt: {backup_dir}")

    restored = []
    for source in backup_dir.rglob("*"):
        if source.is_file():
            destination = ROOT / source.relative_to(backup_dir)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            restored.append(str(destination.relative_to(ROOT)))

    backup_module = backup_dir / NEW_MODULE_TARGET.relative_to(ROOT)
    if not backup_module.exists() and NEW_MODULE_TARGET.exists():
        NEW_MODULE_TARGET.unlink()
        restored.append(f"{NEW_MODULE_TARGET.relative_to(ROOT)} entfernt")

    print("Rollback erfolgreich:")
    for value in restored:
        print(f"- {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
