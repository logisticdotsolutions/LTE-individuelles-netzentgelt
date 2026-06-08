#!/usr/bin/env python3
"""
Lokales Installationspaket für Netzentgelt MVP Phase 5B: Systemvorschläge.

Eigenschaften
-------------
- GitHub-Stand Phase 5A als geprüfte Grundlage
- Dry-Run ohne Schreibzugriff
- kein fragiles Text-Patching: vollständiger Austausch einer eindeutig geprüften UI-Datei
- neue Vorschlags-Engine als separate Datei
- automatische Backups und Rollback
- Python-Syntaxprüfung vor und nach Anwendung
- Erhaltung vorhandener LF- oder CRLF-Zeilenumbrüche
- keine direkte Änderung an GitHub
"""

from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys


PHASE_ID = "NETZENTGELT_MANUAL_OVERRIDE_PHASE5B_V1_20260607"
BACKUP_ROOT_NAME = ".netzentgelt_hotfix_backups"
PAYLOAD_DIR = Path(__file__).resolve().parent / "payload"
UI_RELATIVE = "scripts/manual_override_ui_module.py"
ENGINE_RELATIVE = "scripts/manual_override_suggestion_module.py"
FOUNDATION_MODULE_RELATIVE = "scripts/manual_override_module.py"
APP_RELATIVE = "app/app.py"
RUN_ALL_RELATIVE = "scripts/run_all.py"
ALL_BACKUP_TARGETS = (UI_RELATIVE, ENGINE_RELATIVE)

# GitHub-Blob-SHAs des unmittelbar vor Paketerstellung geprüften main-Stands
# d276d8fb4b07382e1382d4ad9994f0fc636cbc1c.
KNOWN_GITHUB_BLOBS = {
    UI_RELATIVE: "7966929fba47f722a3dcd9b520526efb9f70bc63",
    FOUNDATION_MODULE_RELATIVE: "83f8c360512b768364ab3285baff041e8e030ca4",
    APP_RELATIVE: "4dfcdd217f240a10b3e84ad37079ab3be97b98ee",
    RUN_ALL_RELATIVE: "7f9acb051c69708857054205567e993e487a1692",
}


class PackageError(RuntimeError):
    """Verständlicher Abbruch bei unerwartetem lokalen Stand."""


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def git_blob_sha(raw: bytes) -> str:
    header = f"blob {len(raw)}\0".encode("ascii")
    return hashlib.sha1(header + raw).hexdigest()


def normalize_raw_to_lf(raw: bytes) -> bytes:
    return raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def normalize_text_to_lf(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def detect_newline(raw: bytes) -> str:
    return "\r\n" if b"\r\n" in raw else "\n"


def encode_with_newline(text: str, newline: str) -> bytes:
    text_lf = normalize_text_to_lf(text)
    if newline == "\r\n":
        text_lf = text_lf.replace("\n", "\r\n")
    return text_lf.encode("utf-8")


def syntax_check_text(text: str, label: str) -> None:
    try:
        ast.parse(normalize_text_to_lf(text), filename=label)
    except SyntaxError as exc:
        raise PackageError(f"Python-Syntaxprüfung fehlgeschlagen für {label}: {exc}") from exc


def syntax_check_path(path: Path, label: str) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise PackageError(f"Datei ist nicht UTF-8-dekodierbar: {path}: {exc}") from exc
    syntax_check_text(text, label)


def atomic_write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".phase5b_tmp")
    temporary.write_bytes(raw)
    os.replace(temporary, path)


def _matches_blob(path: Path, expected_blob: str) -> bool:
    raw = path.read_bytes()
    return expected_blob in {git_blob_sha(raw), git_blob_sha(normalize_raw_to_lf(raw))}


def _payload_raw(relative: str, newline: str = "\r\n") -> bytes:
    path = PAYLOAD_DIR / Path(relative).name
    if not path.exists():
        raise PackageError(f"Paket unvollständig: Payload fehlt: {path}")
    text = path.read_text(encoding="utf-8")
    syntax_check_text(text, f"Payload {relative}")
    return encode_with_newline(text, newline)


def _same_normalized(path: Path, expected_raw: bytes) -> bool:
    return path.exists() and normalize_raw_to_lf(path.read_bytes()) == normalize_raw_to_lf(expected_raw)


def _validate_foundation(project_root: Path) -> None:
    required = [UI_RELATIVE, FOUNDATION_MODULE_RELATIVE, APP_RELATIVE, RUN_ALL_RELATIVE]
    missing = [relative for relative in required if not (project_root / relative).exists()]
    if missing:
        raise PackageError("Projektdateien fehlen: " + ", ".join(missing))

    ui_path = project_root / UI_RELATIVE
    ui_payload = _payload_raw(UI_RELATIVE, detect_newline(ui_path.read_bytes()))
    if not _same_normalized(ui_path, ui_payload) and not _matches_blob(ui_path, KNOWN_GITHUB_BLOBS[UI_RELATIVE]):
        raise PackageError(
            "scripts/manual_override_ui_module.py weicht vom geprüften Phase-5A-GitHub-Stand ab. "
            "Keine Dateien wurden verändert. Lokalen Stand prüfen oder zuerst committen."
        )

    foundation_path = project_root / FOUNDATION_MODULE_RELATIVE
    if not _matches_blob(foundation_path, KNOWN_GITHUB_BLOBS[FOUNDATION_MODULE_RELATIVE]):
        text = foundation_path.read_text(encoding="utf-8")
        if "NETZENTGELT_MANUAL_OVERRIDE_PHASE5A_V1_20260607" not in text:
            raise PackageError(
                "scripts/manual_override_module.py enthält nicht die erwartete Phase-5A-Grundlage. "
                "Phase 5B wird nicht angewandt."
            )
        print("HINWEIS: manual_override_module.py wurde lokal erweitert; Phase-5A-Marker ist vorhanden.")

    app_text = (project_root / APP_RELATIVE).read_text(encoding="utf-8")
    if "from manual_override_ui_module import render_manual_override_cockpit" not in app_text:
        raise PackageError("app/app.py enthält die Phase-5A-Cockpitintegration nicht.")

    run_all_text = (project_root / RUN_ALL_RELATIVE).read_text(encoding="utf-8")
    for expected in ["import_manual_overrides", "apply_raw_manual_overrides", "apply_staging_manual_overrides"]:
        if expected not in run_all_text:
            raise PackageError(f"scripts/run_all.py enthält die Phase-5A-Grundlage nicht: {expected} fehlt.")


def _print_blob_info(project_root: Path) -> None:
    print("Geprüfter GitHub-Stand: d276d8fb4b07382e1382d4ad9994f0fc636cbc1c")
    for relative, expected in KNOWN_GITHUB_BLOBS.items():
        path = project_root / relative
        if not path.exists():
            print(f"- {relative}: fehlt")
            continue
        if _matches_blob(path, expected):
            print(f"- {relative}: GitHub-Blob passt ({expected}).")
        else:
            print(f"- {relative}: lokaler Stand weicht ab; Sicherheitsprüfung wird angewandt.")


def _build_target_files(project_root: Path) -> dict[str, bytes]:
    _validate_foundation(project_root)
    ui_path = project_root / UI_RELATIVE
    ui_newline = detect_newline(ui_path.read_bytes())
    return {
        UI_RELATIVE: _payload_raw(UI_RELATIVE, ui_newline),
        ENGINE_RELATIVE: _payload_raw(ENGINE_RELATIVE, "\r\n"),
    }


def _create_backup(project_root: Path) -> Path:
    backup_root = project_root / BACKUP_ROOT_NAME / ("manual_override_phase5b_" + utc_stamp())
    backup_root.mkdir(parents=True, exist_ok=False)
    manifest = {"phase_id": PHASE_ID, "created_at_utc": utc_stamp(), "files": []}

    for relative in ALL_BACKUP_TARGETS:
        source = project_root / relative
        target = backup_root / relative
        existed = source.exists()
        entry = {"relative": relative, "existed": existed}
        if existed:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            entry["sha256"] = sha256_bytes(source.read_bytes())
        manifest["files"].append(entry)

    (backup_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    pointer = project_root / BACKUP_ROOT_NAME / "LATEST_MANUAL_OVERRIDE_PHASE5B.txt"
    pointer.write_text(str(backup_root), encoding="utf-8")
    return backup_root


def apply(project_root: Path, *, dry_run: bool) -> None:
    _print_blob_info(project_root)
    target_files = _build_target_files(project_root)

    print("\nGeprüfte Änderungen:")
    for relative, raw in target_files.items():
        path = project_root / relative
        current = path.read_bytes() if path.exists() else None
        state = "unverändert" if current == raw else ("neu" if current is None else "ändern")
        print(f"- {relative}: {state}")

    if dry_run:
        print("\nDRY RUN erfolgreich. Keine Dateien wurden verändert.")
        return

    backup_root = _create_backup(project_root)
    print(f"\nBackup erstellt: {backup_root}")
    for relative, raw in target_files.items():
        atomic_write(project_root / relative, raw)

    for relative in target_files:
        path = project_root / relative
        if not path.exists():
            raise PackageError(f"Datei fehlt nach Anwendung: {relative}")
        syntax_check_path(path, relative)

    print("Syntaxprüfung nach Anwendung erfolgreich.")
    print("Phase 5B wurde angewandt.")


def rollback(project_root: Path) -> None:
    pointer = project_root / BACKUP_ROOT_NAME / "LATEST_MANUAL_OVERRIDE_PHASE5B.txt"
    if not pointer.exists():
        raise PackageError("Kein Phase-5B-Backup gefunden.")
    backup_root = Path(pointer.read_text(encoding="utf-8").strip())
    manifest_path = backup_root / "manifest.json"
    if not manifest_path.exists():
        raise PackageError(f"Backup-Manifest fehlt: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    for entry in manifest["files"]:
        relative = entry["relative"]
        target = project_root / relative
        backup_file = backup_root / relative
        if entry["existed"]:
            if not backup_file.exists():
                raise PackageError(f"Backup-Datei fehlt: {backup_file}")
            atomic_write(target, backup_file.read_bytes())
        elif target.exists():
            target.unlink()

    print(f"Rollback erfolgreich aus Backup: {backup_root}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--rollback", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = Path(args.project_root).resolve()
    selected = sum(bool(value) for value in [args.dry_run, args.apply, args.rollback])
    if selected != 1:
        raise PackageError("Genau eine Aktion angeben: --dry-run, --apply oder --rollback.")
    if args.rollback:
        rollback(project_root)
    else:
        apply(project_root, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PackageError as exc:
        print(f"FEHLER: {exc}", file=sys.stderr)
        raise SystemExit(1)
