#!/usr/bin/env python3
"""
Lokales Installationspaket für Netzentgelt MVP Phase 5A: manuelle Overrides.

Eigenschaften
-------------
- Dry-Run ohne Schreibzugriff
- abschnittsspezifische und eindeutig geprüfte Suchstellen
- automatische Backups vor jeder Änderung
- atomare Dateiersetzung
- Rollback auf den letzten durch dieses Paket erzeugten Backup-Stand
- Python-Syntaxprüfung vor und nach Anwendung
- Erhaltung vorhandener LF- oder CRLF-Zeilenumbrüche
- keine direkte Änderung an GitHub
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
from datetime import datetime, timezone


PHASE_ID = "NETZENTGELT_MANUAL_OVERRIDE_PHASE5A_V1_20260607"
BACKUP_ROOT_NAME = ".netzentgelt_hotfix_backups"
PAYLOAD_DIR = Path(__file__).resolve().parent / "payload"
NEW_FILES = {
    "scripts/manual_override_module.py": PAYLOAD_DIR / "manual_override_module.py",
    "scripts/manual_override_ui_module.py": PAYLOAD_DIR / "manual_override_ui_module.py",
}
PATCH_FILES = ("scripts/run_all.py", "app/app.py")
ALL_TARGETS = PATCH_FILES + tuple(NEW_FILES.keys())

# GitHub-Blob-SHAs des unmittelbar vor Paketerstellung per Connector geprüften
# main-Stands. Ein lokaler CRLF-Checkout darf raw abweichen; die LF-normalisierte
# Variante wird ebenfalls geprüft und rein informativ ausgegeben.
KNOWN_GITHUB_BLOBS = {
    "scripts/run_all.py": "24b97a49f1dacb2418526e96e676a59cabeae293",
    "app/app.py": "05e36343889852d71a0cb4c451c0703610d358a2",
}


class PatchError(RuntimeError):
    """Verständlicher Abbruch bei nicht eindeutigem oder unerwartetem Stand."""


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def git_blob_sha(raw: bytes) -> str:
    header = f"blob {len(raw)}\0".encode("ascii")
    return hashlib.sha1(header + raw).hexdigest()


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def normalize_raw_to_lf(raw: bytes) -> bytes:
    return raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def detect_newline(raw: bytes) -> str:
    return "\r\n" if b"\r\n" in raw else "\n"


def encode_with_newline(text_lf: str, newline: str) -> bytes:
    text = normalize_newlines(text_lf)
    if newline == "\r\n":
        text = text.replace("\n", "\r\n")
    return text.encode("utf-8")


def read_text_lf(path: Path) -> tuple[str, bytes, str]:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PatchError(f"Datei ist nicht UTF-8-dekodierbar: {path}: {exc}") from exc
    return normalize_newlines(text), raw, detect_newline(raw)


def syntax_check(text: str, label: str) -> None:
    try:
        ast.parse(normalize_newlines(text), filename=label)
    except SyntaxError as exc:
        raise PatchError(f"Python-Syntaxprüfung fehlgeschlagen für {label}: {exc}") from exc


def atomic_write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".phase5a_tmp")
    temporary.write_bytes(raw)
    os.replace(temporary, path)


def function_span(text: str, function_name: str) -> tuple[int, int]:
    pattern = re.compile(rf"(?m)^def {re.escape(function_name)}\(")
    match = pattern.search(text)
    if not match:
        raise PatchError(f"Funktion nicht gefunden: {function_name}")
    next_match = re.compile(r"(?m)^def [A-Za-z_][A-Za-z0-9_]*\(").search(text, match.end())
    return match.start(), next_match.start() if next_match else len(text)


def replace_global_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise PatchError(
            f"Patchstelle '{label}' nicht eindeutig gefunden. Erwartet: 1, gefunden: {count}. "
            "Lokalen Stand prüfen."
        )
    return text.replace(old, new, 1)


def replace_in_function(text: str, function_name: str, old: str, new: str, *, label: str) -> str:
    start, end = function_span(text, function_name)
    block = text[start:end]
    count = block.count(old)
    if count != 1:
        raise PatchError(
            f"Patchstelle '{label}' in Funktion {function_name} nicht eindeutig gefunden. "
            f"Erwartet: 1, gefunden: {count}. Lokalen Stand prüfen."
        )
    block = block.replace(old, new, 1)
    return text[:start] + block + text[end:]


def add_marker_header(text: str) -> str:
    if PHASE_ID in text:
        return text
    return f"# {PHASE_ID}\n" + text


def patch_run_all(text: str) -> str:
    if PHASE_ID in text:
        return text

    text = replace_global_once(
        text,
        "from quality_gate_module import build_quality_gate_tables, refresh_reconciliation_table\n",
        "from quality_gate_module import build_quality_gate_tables, refresh_reconciliation_table\n"
        "from manual_override_module import (\n"
        "    apply_raw_manual_overrides,\n"
        "    apply_staging_manual_overrides,\n"
        "    import_manual_overrides,\n"
        ")\n",
        label="run_all Import manual_override_module",
    )

    text = replace_in_function(
        text,
        "main",
        "        import_vens_tens_exception(con)\n\n"
        "        # 3. Bewegungsdaten und Transport-Routen neu berechnen.\n",
        "        import_vens_tens_exception(con)\n\n"
        "        # Phase 5A: bestätigte manuelle Korrekturen auf die temporär importierten\n"
        "        # Rohdaten anwenden. Original-CSVs bleiben unverändert.\n"
        "        import_manual_overrides(con)\n"
        "        apply_raw_manual_overrides(con, run_id)\n\n"
        "        # 3. Bewegungsdaten und Transport-Routen neu berechnen.\n",
        label="run_all Overrides nach Mappingimport",
    )

    text = replace_in_function(
        text,
        "main",
        "        build_loco_events(con)\n"
        "        build_transport_routes(con)\n",
        "        build_loco_events(con)\n"
        "        apply_staging_manual_overrides(con, run_id)\n"
        "        build_transport_routes(con)\n",
        label="run_all Staging-Overrides vor Routenerkennung",
    )

    text = replace_in_function(
        text,
        "main",
        "            (\"audit_excluded_cancelled_transports\", \"audit_excluded_cancelled_transports.csv\"),\n",
        "            (\"audit_excluded_cancelled_transports\", \"audit_excluded_cancelled_transports.csv\"),\n"
        "            (\"cfg_manual_overrides\", \"cfg_manual_overrides.csv\"),\n"
        "            (\"cfg_manual_overrides_effective\", \"cfg_manual_overrides_effective.csv\"),\n"
        "            (\"dq_manual_override_conflicts\", \"dq_manual_override_conflicts.csv\"),\n"
        "            (\"audit_manual_override_application\", \"audit_manual_override_application.csv\"),\n",
        label="run_all Override-Audit CSV-Exporte",
    )

    return add_marker_header(text)


def patch_app(text: str) -> str:
    if PHASE_ID in text:
        return text

    text = replace_global_once(
        text,
        "from operator_ui_module import render_operator_dashboard, render_open_tasks\n",
        "from operator_ui_module import render_operator_dashboard, render_open_tasks\n"
        "from manual_override_ui_module import render_manual_override_cockpit\n",
        label="app Import manual_override_ui_module",
    )

    text = replace_global_once(
        text,
        "tab_overview, tab_tasks, tab_timeline, tab_exports, tab_no_loco, tab_findings, tab_run = st.tabs([\n"
        "    \"1. Tagesprüfung\",\n"
        "    \"2. Offene Aufgaben\",\n"
        "    \"3. Lok prüfen\",\n"
        "    \"4. Exporte erstellen\",\n"
        "    \"⚙️ Technik: Loknummern\",\n"
        "    \"⚙️ Technik: Regelqueue\",\n"
        "    \"⚙️ Technik: Pipeline\"\n"
        "])\n",
        "tab_overview, tab_tasks, tab_override, tab_timeline, tab_exports, tab_no_loco, tab_findings, tab_run = st.tabs([\n"
        "    \"1. Tagesprüfung\",\n"
        "    \"2. Offene Aufgaben\",\n"
        "    \"3. Fall bearbeiten\",\n"
        "    \"4. Lok prüfen\",\n"
        "    \"5. Exporte erstellen\",\n"
        "    \"⚙️ Technik: Loknummern\",\n"
        "    \"⚙️ Technik: Regelqueue\",\n"
        "    \"⚙️ Technik: Pipeline\"\n"
        "])\n",
        label="app Navigation Fall bearbeiten",
    )

    text = replace_global_once(
        text,
        "with tab_tasks:\n"
        "    render_open_tasks(\n"
        "        export_gate=export_gate,\n"
        "        global_export_blockers=global_export_blockers,\n"
        "        findings=findings,\n"
        "    )\n\n\n"
        "with tab_no_loco:\n",
        "with tab_tasks:\n"
        "    render_open_tasks(\n"
        "        export_gate=export_gate,\n"
        "        global_export_blockers=global_export_blockers,\n"
        "        findings=findings,\n"
        "    )\n\n\n"
        "with tab_override:\n"
        "    render_manual_override_cockpit(\n"
        "        db_path=DB_PATH,\n"
        "        run_all_script=SCRIPT_RUN_ALL,\n"
        "        findings=findings,\n"
        "        timeline=timeline_raw,\n"
        "    )\n\n\n"
        "with tab_no_loco:\n",
        label="app Render Fall bearbeiten",
    )

    return add_marker_header(text)


PATCHERS = {
    "scripts/run_all.py": patch_run_all,
    "app/app.py": patch_app,
}


def _validate_project_root(project_root: Path) -> None:
    missing = [relative for relative in PATCH_FILES if not (project_root / relative).exists()]
    if missing:
        raise PatchError("Projektdateien fehlen: " + ", ".join(missing))
    for relative, payload in NEW_FILES.items():
        if not payload.exists():
            raise PatchError(f"Paket unvollständig: Payload fehlt: {payload}")
        syntax_check(payload.read_text(encoding="utf-8"), f"Payload {relative}")


def _print_blob_info(project_root: Path) -> None:
    for relative, expected in KNOWN_GITHUB_BLOBS.items():
        raw = (project_root / relative).read_bytes()
        raw_blob = git_blob_sha(raw)
        lf_blob = git_blob_sha(normalize_raw_to_lf(raw))
        if expected in {raw_blob, lf_blob}:
            print(f"GitHub-Stand geprüft: {relative} passt ({expected}).")
        else:
            print(
                "HINWEIS: Lokaler Stand weicht vom geprüften GitHub-Blob ab: "
                f"{relative}. Dry-Run prüft deshalb zusätzlich alle Anker streng."
            )


def build_patched_files(project_root: Path) -> dict[str, bytes]:
    _validate_project_root(project_root)
    result: dict[str, bytes] = {}

    for relative in PATCH_FILES:
        path = project_root / relative
        text, _, newline = read_text_lf(path)
        patched = PATCHERS[relative](text)
        syntax_check(patched, relative)
        result[relative] = encode_with_newline(patched, newline)

    for relative, payload_path in NEW_FILES.items():
        payload_text = normalize_newlines(payload_path.read_text(encoding="utf-8"))
        syntax_check(payload_text, relative)
        result[relative] = encode_with_newline(payload_text, "\r\n")

    return result


def _create_backup(project_root: Path) -> Path:
    backup_root = project_root / BACKUP_ROOT_NAME / ("manual_override_phase5a_" + utc_stamp())
    backup_root.mkdir(parents=True, exist_ok=False)
    manifest = {"phase_id": PHASE_ID, "created_at_utc": utc_stamp(), "files": []}

    for relative in ALL_TARGETS:
        source = project_root / relative
        target = backup_root / relative
        existed = source.exists()
        entry = {"relative": relative, "existed": existed}
        if existed:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            raw = source.read_bytes()
            entry["sha256"] = sha256_bytes(raw)
        manifest["files"].append(entry)

    (backup_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (project_root / BACKUP_ROOT_NAME / "LATEST_MANUAL_OVERRIDE_PHASE5A.txt").write_text(
        str(backup_root), encoding="utf-8"
    )
    return backup_root


def apply(project_root: Path, *, dry_run: bool) -> None:
    _print_blob_info(project_root)
    patched = build_patched_files(project_root)

    print("\nGeprüfte Änderungen:")
    for relative, raw in patched.items():
        current = (project_root / relative).read_bytes() if (project_root / relative).exists() else None
        state = "unverändert" if current == raw else ("neu" if current is None else "ändern")
        print(f"- {relative}: {state}")

    if dry_run:
        print("\nDRY RUN erfolgreich. Keine Dateien wurden verändert.")
        return

    backup_dir = _create_backup(project_root)
    print(f"\nBackup erstellt: {backup_dir}")
    for relative, raw in patched.items():
        atomic_write(project_root / relative, raw)

    # Abschlussprüfung direkt gegen die tatsächlich geschriebenen Dateien.
    for relative in ALL_TARGETS:
        path = project_root / relative
        if not path.exists():
            raise PatchError(f"Datei fehlt nach Anwendung: {relative}")
        syntax_check(path.read_text(encoding="utf-8"), relative)

    print("Syntaxprüfung nach Anwendung erfolgreich.")
    print("Phase 5A wurde angewandt.")


def rollback(project_root: Path) -> None:
    latest_pointer = project_root / BACKUP_ROOT_NAME / "LATEST_MANUAL_OVERRIDE_PHASE5A.txt"
    if not latest_pointer.exists():
        raise PatchError("Kein Phase-5A-Backup gefunden.")
    backup_root = Path(latest_pointer.read_text(encoding="utf-8").strip())
    manifest_path = backup_root / "manifest.json"
    if not manifest_path.exists():
        raise PatchError(f"Backup-Manifest fehlt: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    for entry in manifest["files"]:
        relative = entry["relative"]
        target = project_root / relative
        backup_file = backup_root / relative
        if entry["existed"]:
            if not backup_file.exists():
                raise PatchError(f"Backup-Datei fehlt: {backup_file}")
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
        raise PatchError("Genau eine Aktion angeben: --dry-run, --apply oder --rollback.")
    if args.rollback:
        rollback(project_root)
    else:
        apply(project_root, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PatchError as exc:
        print(f"FEHLER: {exc}", file=sys.stderr)
        raise SystemExit(1)
