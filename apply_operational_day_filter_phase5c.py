from __future__ import annotations

import argparse
import json
import os
import py_compile
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

PHASE_ID = "NETZENTGELT_OPERATIONAL_DAY_FILTER_PHASE5C_V1_20260608"
ROOT = Path(__file__).resolve().parent
PAYLOAD = ROOT / "payload"
BACKUP_ROOT_NAME = ".netzentgelt_hotfix_backups"
LATEST_FILE = ROOT / ".phase5c_latest_backup.txt"

TARGETS = [
    Path("app/app.py"),
    Path("scripts/manual_override_ui_module.py"),
    Path("scripts/operational_day_filter_module.py"),
]

APP_IMPORT_OLD = """from manual_override_ui_module import render_manual_override_cockpit\n# ------------------------------------------------------\n"""
APP_IMPORT_NEW = """from manual_override_ui_module import render_manual_override_cockpit\nfrom operational_day_filter_module import (\n    filter_by_operational_days,\n    render_sidebar_operational_day_filter,\n    summarize_no_loco_cases,\n)\n# NETZENTGELT_OPERATIONAL_DAY_FILTER_PHASE5C_V1_20260608\n# ------------------------------------------------------\n"""

APP_INSERT_OLD = """    st.exception(diagnostics_error)\n\ntab_overview, tab_tasks, tab_override, tab_timeline, tab_exports, tab_no_loco, tab_findings, tab_run = st.tabs([\n"""
APP_INSERT_NEW = """    st.exception(diagnostics_error)\n\n# ==================================================\n# NETZENTGELT_OPERATIONAL_DAY_FILTER_PHASE5C_V1_20260608\n# Einheitlicher operativer Tagesfilter. Die Uhrzeit wird bewusst ignoriert.\n# Fuer Movements ist ActualDeparture massgeblich; GAPs verwenden ihren\n# fachlich abgeleiteten Periodenbeginn als defensiven Fallback.\n# ==================================================\noperational_day_from, operational_day_to = render_sidebar_operational_day_filter()\n\ntimeline_raw = filter_by_operational_days(\n    timeline_raw,\n    date_from=operational_day_from,\n    date_to=operational_day_to,\n    timestamp_candidates=[\"actual_departure_ts\", \"ActualDeparture\", \"period_start_utc\"],\n)\ntimeline = hide_non_relevant_gap_rows(timeline_raw)\nfindings = filter_by_operational_days(\n    findings,\n    date_from=operational_day_from,\n    date_to=operational_day_to,\n    timestamp_candidates=[\"actual_departure_ts\", \"ActualDeparture\", \"period_start_utc\"],\n)\ncoverage = filter_by_operational_days(\n    coverage,\n    date_from=operational_day_from,\n    date_to=operational_day_to,\n    timestamp_candidates=[\"coverage_date\"],\n)\nexport_gate = filter_by_operational_days(\n    export_gate,\n    date_from=operational_day_from,\n    date_to=operational_day_to,\n    timestamp_candidates=[\"coverage_date\"],\n)\nexport_gate_ru = filter_by_operational_days(\n    export_gate_ru,\n    date_from=operational_day_from,\n    date_to=operational_day_to,\n    timestamp_candidates=[\"coverage_date\"],\n)\nglobal_export_blockers = filter_by_operational_days(\n    global_export_blockers,\n    date_from=operational_day_from,\n    date_to=operational_day_to,\n    timestamp_candidates=[\"blocker_date\", \"period_start_utc\"],\n)\nexcluded_export_rows = filter_by_operational_days(\n    excluded_export_rows,\n    date_from=operational_day_from,\n    date_to=operational_day_to,\n    timestamp_candidates=[\"actual_departure_ts\", \"ActualDeparture\", \"period_start_utc\", \"coverage_date\"],\n)\nno_loco_cases = filter_by_operational_days(\n    no_loco_cases,\n    date_from=operational_day_from,\n    date_to=operational_day_to,\n    timestamp_candidates=[\"Erstes Datum\"],\n)\nno_loco_summary = summarize_no_loco_cases(no_loco_cases, no_loco_summary)\n\ntab_overview, tab_tasks, tab_override, tab_timeline, tab_exports, tab_no_loco, tab_findings, tab_run = st.tabs([\n"""

APP_LEGEND_OLD = """                \"auf den aktuellen Datenlauf vor Anwendung der Filter.\"\n"""
APP_LEGEND_NEW = """                \"auf den aktuell gewaehlten Arbeitszeitraum vor Anwendung der weiteren Filter.\"\n"""

UI_CAPTION_OLD = """    st.caption(\n        \"Originaldaten bleiben unverändert. Das Tool schlägt nachvollziehbare Werte vor; \"\n        \"eine fachliche Entscheidung und bewusste Bestätigung bleiben erforderlich.\"\n    )\n"""
UI_CAPTION_NEW = """    st.warning(\n        \"Wichtig: Eine Korrektur in diesem Tool ändert keine Daten in RailCube. \"\n        \"Fachlich erforderliche Berichtigungen müssen zusätzlich in RailCube nachgezogen werden.\"\n    )\n    st.info(\n        \"Aktive Overrides bleiben bei einem neuen Rohdatenimport erhalten und werden bei jedem \"\n        \"run_all.py erneut auf den frischen Import angewandt. Sobald RailCube korrigiert wurde, \"\n        \"den zugehörigen Override bitte deaktivieren. Findet ein Override keinen passenden \"\n        \"Datensatz mehr, wird dies im Audit als NO_MATCH dokumentiert.\"\n    )\n    st.caption(\n        \"Originaldaten bleiben unverändert. Das Tool schlägt nachvollziehbare Werte vor; \"\n        \"eine fachliche Entscheidung und bewusste Bestätigung bleiben erforderlich.\"\n    )\n"""

UI_AUDIT_OLD = """    st.markdown(\"#### Phase-5B-Grenze\")\n"""
UI_AUDIT_NEW = """    st.markdown(\"#### Zusammenspiel mit RailCube und neuen Importen\")\n    st.info(\n        \"Overrides sind eine lokale, auditierbare Korrekturschicht dieses Tools. Sie werden nicht \"\n        \"nach RailCube zurückgeschrieben. Bei einem neuen Import bleiben aktive Overrides bestehen \"\n        \"und werden erneut angewandt. Nach einer Berichtigung in RailCube bitte den lokalen Override \"\n        \"deaktivieren, damit dauerhaft wieder der RailCube-Quellwert verwendet wird.\"\n    )\n    st.markdown(\"#### Phase-5B-Grenze\")\n"""


def read_text(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    newline = "\r\n" if b"\r\n" in raw else "\n"
    text = raw.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    return text, newline


def write_text(path: Path, text: str, newline: str) -> None:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(normalized.replace("\n", newline).encode("utf-8"))


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Patchstelle '{label}' nicht eindeutig gefunden. Erwartet: 1, gefunden: {count}.")
    return text.replace(old, new, 1)


def patched_files(project_root: Path) -> dict[Path, tuple[str, str]]:
    app_path = project_root / "app/app.py"
    ui_path = project_root / "scripts/manual_override_ui_module.py"
    if not app_path.exists() or not ui_path.exists():
        raise RuntimeError("Erwartete Projektdateien fehlen. Bitte im Projektstamm ausführen.")

    app_text, app_newline = read_text(app_path)
    ui_text, ui_newline = read_text(ui_path)

    if PHASE_ID in app_text:
        # Bereits installiert: dennoch Syntaxprüfung über bestehende Dateien erlauben.
        return {
            Path("app/app.py"): (app_text, app_newline),
            Path("scripts/manual_override_ui_module.py"): (ui_text, ui_newline),
            Path("scripts/operational_day_filter_module.py"): read_text(project_root / "scripts/operational_day_filter_module.py"),
        }

    if "NETZENTGELT_MANUAL_OVERRIDE_PHASE5B_UI_V1_20260607" not in ui_text:
        raise RuntimeError("Phase 5B wurde nicht erkannt. Zuerst aktuellen GitHub-Stand prüfen.")

    app_text = replace_once(app_text, APP_IMPORT_OLD, APP_IMPORT_NEW, "app Import Tagesfilter")
    app_text = replace_once(app_text, APP_INSERT_OLD, APP_INSERT_NEW, "app zentrale Tagesfilterung")
    app_text = replace_once(app_text, APP_LEGEND_OLD, APP_LEGEND_NEW, "app Legendentext Arbeitszeitraum")
    ui_text = replace_once(ui_text, UI_CAPTION_OLD, UI_CAPTION_NEW, "Override-Cockpit RailCube-Hinweis")
    ui_text = replace_once(ui_text, UI_AUDIT_OLD, UI_AUDIT_NEW, "Override-Audit Importhinweis")

    helper_text, helper_newline = read_text(PAYLOAD / "scripts/operational_day_filter_module.py")
    return {
        Path("app/app.py"): (app_text, app_newline),
        Path("scripts/manual_override_ui_module.py"): (ui_text, ui_newline),
        Path("scripts/operational_day_filter_module.py"): (helper_text, helper_newline),
    }


def compile_candidate(relative: Path, text: str) -> None:
    compile(text, str(relative), "exec")


def create_backup(project_root: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = project_root / BACKUP_ROOT_NAME / f"operational_day_filter_phase5c_{stamp}"
    counter = 1
    while backup_dir.exists():
        backup_dir = project_root / BACKUP_ROOT_NAME / f"operational_day_filter_phase5c_{stamp}_{counter}"
        counter += 1
    backup_dir.mkdir(parents=True)
    manifest = {"phase_id": PHASE_ID, "created_at_utc": stamp, "files": []}
    for relative in TARGETS:
        source = project_root / relative
        record = {"relative": str(relative).replace("\\", "/"), "existed": source.exists()}
        if source.exists():
            target = backup_dir / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        manifest["files"].append(record)
    (backup_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    LATEST_FILE.write_text(str(backup_dir), encoding="utf-8")
    return backup_dir


def rollback(project_root: Path) -> None:
    if not LATEST_FILE.exists():
        raise RuntimeError("Kein Phase-5C-Backupverweis gefunden.")
    backup_dir = Path(LATEST_FILE.read_text(encoding="utf-8").strip())
    manifest = json.loads((backup_dir / "manifest.json").read_text(encoding="utf-8"))
    for record in manifest["files"]:
        relative = Path(record["relative"])
        target = project_root / relative
        backup = backup_dir / relative
        if record["existed"]:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup, target)
        elif target.exists():
            target.unlink()
    print(f"Rollback abgeschlossen: {backup_dir}")


def verify(project_root: Path) -> None:
    required = [
        project_root / "app/app.py",
        project_root / "scripts/manual_override_ui_module.py",
        project_root / "scripts/operational_day_filter_module.py",
    ]
    for path in required:
        if not path.exists():
            raise RuntimeError(f"Datei fehlt: {path}")
        text, _ = read_text(path)
        compile_candidate(path, text)
    app_text, _ = read_text(project_root / "app/app.py")
    ui_text, _ = read_text(project_root / "scripts/manual_override_ui_module.py")
    if PHASE_ID not in app_text:
        raise RuntimeError("Phase-5C-Marker fehlt in app/app.py")
    if "Eine Korrektur in diesem Tool ändert keine Daten in RailCube" not in ui_text:
        raise RuntimeError("RailCube-Hinweis fehlt im Override-Cockpit")
    print("VERIFY erfolgreich: Syntax, Marker und RailCube-Hinweis geprüft.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["dry-run", "apply", "verify", "rollback"])
    parser.add_argument("--project-root", default=".")
    args = parser.parse_args()
    project_root = Path(args.project_root).resolve()

    if args.mode == "rollback":
        rollback(project_root)
        return 0
    if args.mode == "verify":
        verify(project_root)
        return 0

    candidates = patched_files(project_root)
    for relative, (text, _newline) in candidates.items():
        compile_candidate(relative, text)
    print("Patch-Kandidaten syntaktisch gültig.")

    if args.mode == "dry-run":
        print("DRY RUN erfolgreich. Keine Dateien wurden verändert.")
        return 0

    backup_dir = create_backup(project_root)
    for relative, (text, newline) in candidates.items():
        write_text(project_root / relative, text, newline)
    verify(project_root)
    print(f"APPLY erfolgreich. Backup: {backup_dir}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"FEHLER: {error}", file=sys.stderr)
        raise
