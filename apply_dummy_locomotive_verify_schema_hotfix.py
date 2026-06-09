from __future__ import annotations

import argparse
import hashlib
import py_compile
import shutil
from datetime import datetime, timezone
from pathlib import Path

MARKER = "NETZENTGELT_DUMMY_LOCOMOTIVE_VERIFY_SCHEMA_HOTFIX_V1_20260609"
ROOT = Path(__file__).resolve().parent
TARGET = Path("scripts/verify_dummy_locomotive_hardening.py")
PAYLOAD = ROOT / "payload" / TARGET
BACKUP_ROOT = Path(".dummy_locomotive_verify_schema_hotfix_backups")
EXPECTED_OLD_GIT_BLOB = "7e4a93356d947ad4176880b454de158845ca413f"


def lf_bytes(raw: bytes) -> bytes:
    return raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def git_blob_sha(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def has_only_crlf(raw: bytes) -> bool:
    return b"\n" not in raw.replace(b"\r\n", b"")


def state(project: Path) -> str:
    path = project / TARGET
    if not path.exists():
        raise RuntimeError(f"Datei fehlt: {TARGET}. Zuerst Dummy-Lokomotiven-Hardening anwenden.")
    raw = path.read_bytes()
    text = lf_bytes(raw).decode("utf-8")
    if MARKER in text:
        return "installed"
    actual = git_blob_sha(lf_bytes(raw))
    if actual != EXPECTED_OLD_GIT_BLOB:
        raise RuntimeError(
            f"Lokaler Stand von '{TARGET}' ist unbekannt. Erwarteter Alt-Blob: {EXPECTED_OLD_GIT_BLOB}, lokal: {actual}."
        )
    return "original"


def verify_payload() -> None:
    if not PAYLOAD.exists():
        raise RuntimeError(f"Payload fehlt: {PAYLOAD}")
    raw = PAYLOAD.read_bytes()
    if MARKER.encode("utf-8") not in raw:
        raise RuntimeError("Marker fehlt im Payload.")
    if not has_only_crlf(raw):
        raise RuntimeError("Payload enthält Text ohne Windows-CRLF.")
    py_compile.compile(str(PAYLOAD), doraise=True)


def verify_installed(project: Path) -> None:
    path = project / TARGET
    raw = path.read_bytes()
    if MARKER.encode("utf-8") not in raw:
        raise RuntimeError("Marker fehlt in installierter Datei.")
    if not has_only_crlf(raw):
        raise RuntimeError("Installierte Datei enthält Text ohne Windows-CRLF.")
    py_compile.compile(str(path), doraise=True)


def dry_run(project: Path) -> int:
    verify_payload()
    current = state(project)
    print(f"OK: Dry Run erfolgreich. Zustand={current}. Keine Dateien wurden veraendert.")
    return 0


def apply(project: Path) -> int:
    verify_payload()
    current = state(project)
    if current == "installed":
        verify_installed(project)
        print("OK: Verify-Schema-Hotfix ist bereits installiert.")
        return 0
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%f")
    backup = project / BACKUP_ROOT / stamp
    backup.mkdir(parents=True, exist_ok=True)
    shutil.copy2(project / TARGET, backup / TARGET.name)
    (backup / "TARGET.txt").write_text(str(TARGET), encoding="utf-8")
    shutil.copy2(PAYLOAD, project / TARGET)
    verify_installed(project)
    print(f"OK: Verify-Schema-Hotfix angewandt. Backup: {backup}")
    return 0


def verify(project: Path) -> int:
    verify_payload()
    if state(project) != "installed":
        raise RuntimeError("Hotfix ist noch nicht installiert.")
    verify_installed(project)
    print("OK: Marker, CRLF und Python-Syntax verifiziert.")
    return 0


def rollback(project: Path) -> int:
    root = project / BACKUP_ROOT
    backups = sorted([p for p in root.glob("*") if p.is_dir()]) if root.exists() else []
    if not backups:
        raise RuntimeError("Kein Backup fuer Rollback vorhanden.")
    backup = backups[-1]
    shutil.copy2(backup / TARGET.name, project / TARGET)
    print(f"OK: Rollback aus {backup} wiederhergestellt.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["dry-run", "apply", "verify", "rollback"])
    parser.add_argument("--project", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        return {"dry-run": dry_run, "apply": apply, "verify": verify, "rollback": rollback}[args.command](args.project.resolve())
    except Exception as exc:
        print(f"FEHLER: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
