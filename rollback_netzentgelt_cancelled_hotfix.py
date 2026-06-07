from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKUP_ROOT = ROOT / ".patch_backups"
PREFIX = "netzentgelt_cancelled_filter_hotfix_"

TARGETS = [
    Path("scripts/run_all.py"),
    Path("scripts/error_rules.py"),
    Path("scripts/export_module.py"),
    Path("app/app.py"),
]


def main() -> int:
    if not BACKUP_ROOT.exists():
        raise RuntimeError("Kein Backup-Ordner gefunden.")

    candidates = sorted(
        [path for path in BACKUP_ROOT.iterdir() if path.is_dir() and path.name.startswith(PREFIX)],
        reverse=True,
    )
    if not candidates:
        raise RuntimeError("Kein Cancelled-Hotfix-Backup gefunden.")

    backup_dir = candidates[0]
    for relative in TARGETS:
        source = backup_dir / relative
        if not source.exists():
            raise RuntimeError(f"Backup-Datei fehlt: {source}")
        target = ROOT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    print(f"Rollback erfolgreich aus Backup: {backup_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
