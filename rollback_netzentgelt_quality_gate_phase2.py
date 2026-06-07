from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LAST_BACKUP_FILE = ROOT / ".quality_gate_phase2_last_backup.txt"
QUALITY_MODULE = ROOT / "scripts" / "quality_gate_module.py"


def main() -> int:
    if not LAST_BACKUP_FILE.exists():
        raise RuntimeError(
            "Kein Phase-2-Backupzeiger gefunden. Rollback kann nicht automatisch ausgeführt werden."
        )

    backup_dir = Path(LAST_BACKUP_FILE.read_text(encoding="utf-8").strip())

    if not backup_dir.exists():
        raise RuntimeError(f"Backup-Ordner fehlt: {backup_dir}")

    backup_quality_module = backup_dir / "scripts" / "quality_gate_module.py"

    if QUALITY_MODULE.exists() and not backup_quality_module.exists():
        QUALITY_MODULE.unlink()
        print(f"Entfernt: {QUALITY_MODULE.relative_to(ROOT)}")

    restored = 0

    for source in backup_dir.rglob("*"):
        if not source.is_file():
            continue

        destination = ROOT / source.relative_to(backup_dir)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        restored += 1
        print(f"Wiederhergestellt: {destination.relative_to(ROOT)}")

    print(f"Rollback abgeschlossen. Wiederhergestellte Dateien: {restored}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
