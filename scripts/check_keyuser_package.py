from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "_keyuser_package" / "NetzentgeltMVP_KeyUser"

NEEDED = [
    "NetzentgeltMVP.exe",
    "START_HIER.txt",
    "app/secure_app.py",
    "app/secure_app_portable.py",
    "scripts/download_blob_data.py",
    "scripts/run_all.py",
    "scripts/packaged_subprocess_runtime_bridge.py",
    "scripts/full_import_lock_runtime_module.py",
    "data/00_raw",
    "data/01_mapping",
    "data/02_duckdb",
    "data/03_exports",
]

USERS = [
    "data/02_duckdb/app_state/netzentgelt_app_state.sqlite",
    "config/prepared_users.csv",
]


def main() -> int:
    missing = []
    for rel in NEEDED:
        if not (PKG / rel).exists():
            missing.append(rel)

    if missing:
        print("FAIL: Paket unvollstaendig")
        for rel in missing:
            print("- " + rel)
        return 1

    if not any((PKG / rel).exists() for rel in USERS):
        print("WARNING: keine vorbereitete Benutzerdatei gefunden")

    print("PASS: Paketdateien vorhanden")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
