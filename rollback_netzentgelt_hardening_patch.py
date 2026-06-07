from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys

TARGET_FILES = [
    Path("scripts/download_blob_data.py"),
    Path("scripts/run_all.py"),
    Path("scripts/error_rules.py"),
    Path("scripts/export_module.py"),
    Path("app/app.py"),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Letztes Netzentgelt-Hardening zurückrollen.")
    parser.add_argument("--repo-root", help="Projektstamm, Standard: aktueller Ordner")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve() if args.repo_root else Path.cwd().resolve()
    marker = root / ".patch_backups" / "LAST_NETZENTGELT_HARDENING_BACKUP.txt"

    if not marker.exists():
        print("Kein Hardening-Backup gefunden.", file=sys.stderr)
        return 1

    backup_dir = Path(marker.read_text(encoding="utf-8").strip())
    if not backup_dir.exists():
        print(f"Backup-Ordner fehlt: {backup_dir}", file=sys.stderr)
        return 1

    for relative_path in TARGET_FILES:
        source = backup_dir / relative_path
        target = root / relative_path

        if not source.exists():
            print(f"Backup-Datei fehlt: {source}", file=sys.stderr)
            return 1

        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        print(f"Wiederhergestellt: {relative_path}")

    print("Rollback abgeschlossen.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
