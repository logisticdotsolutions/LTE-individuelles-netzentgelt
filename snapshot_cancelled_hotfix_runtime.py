from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKUP_POINTER = ROOT / ".cancelled_hotfix_v2_last_runtime_backup.txt"
DB_RELATIVE = Path("data/02_duckdb/netzentgelt.duckdb")
EXPORT_DIR_RELATIVE = Path("data/03_exports")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def backup_runtime() -> Path:
    backup_dir = ROOT / ".patch_backups" / (
        "netzentgelt_cancelled_runtime_v2_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    backup_dir.mkdir(parents=True, exist_ok=False)

    manifest = {
        "db_relative": DB_RELATIVE.as_posix(),
        "db_existed": False,
        "db_sha256": None,
        "exports_relative": EXPORT_DIR_RELATIVE.as_posix(),
        "exports_existed": False,
        "export_files": {},
    }

    db_path = ROOT / DB_RELATIVE
    if db_path.exists():
        target = backup_dir / DB_RELATIVE
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(db_path, target)
        manifest["db_existed"] = True
        manifest["db_sha256"] = sha256(target)

    export_dir = ROOT / EXPORT_DIR_RELATIVE
    if export_dir.exists():
        target_dir = backup_dir / EXPORT_DIR_RELATIVE
        shutil.copytree(export_dir, target_dir)
        manifest["exports_existed"] = True
        for file_path in sorted(target_dir.rglob("*")):
            if file_path.is_file():
                relative = file_path.relative_to(target_dir).as_posix()
                manifest["export_files"][relative] = sha256(file_path)

    (backup_dir / "runtime_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    BACKUP_POINTER.write_text(str(backup_dir), encoding="utf-8")
    print(f"Runtime-Backup erstellt: {backup_dir}")
    return backup_dir


def restore_runtime(if_present: bool) -> None:
    if not BACKUP_POINTER.exists():
        if if_present:
            print("Kein Runtime-Backup vorhanden. Datenstand bleibt unverändert.")
            return
        raise RuntimeError("Kein Runtime-Backup registriert.")

    backup_dir = Path(BACKUP_POINTER.read_text(encoding="utf-8").strip())
    manifest_path = backup_dir / "runtime_manifest.json"
    if not manifest_path.exists():
        raise RuntimeError(f"Runtime-Manifest fehlt: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    db_path = ROOT / Path(manifest["db_relative"])
    db_backup = backup_dir / Path(manifest["db_relative"])
    if manifest["db_existed"]:
        if not db_backup.exists():
            raise RuntimeError(f"Gesicherte DuckDB fehlt: {db_backup}")
        if sha256(db_backup) != manifest["db_sha256"]:
            raise RuntimeError("DuckDB-Backup-Prüfsumme ungültig.")
        db_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(db_backup, db_path)
    elif db_path.exists():
        db_path.unlink()

    export_dir = ROOT / Path(manifest["exports_relative"])
    export_backup_dir = backup_dir / Path(manifest["exports_relative"])
    if export_dir.exists():
        shutil.rmtree(export_dir)

    if manifest["exports_existed"]:
        if not export_backup_dir.exists():
            raise RuntimeError(f"Gesicherter Exportordner fehlt: {export_backup_dir}")
        for relative, expected_hash in manifest["export_files"].items():
            backup_file = export_backup_dir / relative
            if not backup_file.exists() or sha256(backup_file) != expected_hash:
                raise RuntimeError(f"Export-Backup-Prüfsumme ungültig: {relative}")
        shutil.copytree(export_backup_dir, export_dir)

    print(f"Runtime-Rollback erfolgreich aus Backup: {backup_dir}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Runtime-Snapshot für Netzentgelt Cancelled-Hotfix V2")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--backup", action="store_true")
    action.add_argument("--restore-latest", action="store_true")
    action.add_argument("--restore-latest-if-present", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.backup:
        backup_runtime()
    elif args.restore_latest:
        restore_runtime(if_present=False)
    elif args.restore_latest_if_present:
        restore_runtime(if_present=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("")
        print(f"FEHLER: {exc}")
        raise
