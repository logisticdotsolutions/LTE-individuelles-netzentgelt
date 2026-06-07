from __future__ import annotations

import argparse
import datetime as dt
import py_compile
import re
import shutil
from pathlib import Path

MARKER = "NETZENTGELT_DAU_UX_PHASE3_V1_20260607"
PHASE2_MARKER = "NETZENTGELT_QUALITY_GATE_PHASE2_V1_20260607"
ROOT = Path(__file__).resolve().parent
APP_PATH = ROOT / "app" / "app.py"
PHASE2_MODULE = ROOT / "scripts" / "quality_gate_module.py"
PAYLOAD = ROOT / "payload" / "operator_ui_module.py"
NEW_MODULE_TARGET = ROOT / "scripts" / "operator_ui_module.py"
BACKUP_ROOT = ROOT / ".patch_backups"
LAST_BACKUP_FILE = ROOT / ".dau_ux_phase3_last_backup.txt"


def read_text_preserve_bom(path: Path) -> tuple[str, bool, str]:
    raw = path.read_bytes()
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    decoded = raw.decode("utf-8-sig")
    newline_style = "\r\n" if "\r\n" in decoded else "\n"
    normalized = decoded.replace("\r\n", "\n").replace("\r", "\n")
    return normalized, has_bom, newline_style


def write_text_preserve_bom(path: Path, text: str, has_bom: bool, newline_style: str) -> None:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    rendered = normalized if newline_style == "\n" else normalized.replace("\n", newline_style)
    raw = rendered.encode("utf-8")
    if has_bom:
        raw = b"\xef\xbb\xbf" + raw
    path.write_bytes(raw)


def require_path(path: Path) -> None:
    if not path.exists():
        raise RuntimeError(f"Erwartete Datei fehlt: {path}")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"Patchstelle '{label}' nicht eindeutig gefunden. "
            f"Erwartet: 1, gefunden: {count}. "
            "Bitte zuerst Phase 2 v1.1 vollstaendig anwenden und die Pipeline ausfuehren."
        )
    return text.replace(old, new, 1)


def insert_after_once(text: str, anchor: str, addition: str, label: str) -> str:
    return replace_once(text, anchor, anchor + addition, label)


def patch_app(text: str) -> str:
    if MARKER in text:
        return text

    if PHASE2_MARKER not in text:
        raise RuntimeError(
            "Phase-2-Marker fehlt in app/app.py. Bitte zuerst das Paket "
            "netzentgelt_quality_gate_phase2_v1_1 anwenden und die Pipeline ausfuehren."
        )

    export_import_pattern = re.compile(
        r"(from export_module import \(\n(?:    .*\n)+?\)\n)",
        re.MULTILINE,
    )
    match = export_import_pattern.search(text)
    if not match:
        raise RuntimeError("Importblock aus export_module wurde in app/app.py nicht gefunden.")

    import_addition = (
        match.group(1)
        + "from operator_ui_module import render_operator_dashboard, render_open_tasks\n"
    )
    text = text[: match.start()] + import_addition + text[match.end() :]

    old_tabs = '''tab_overview, tab_no_loco, tab_timeline, tab_findings, tab_exports, tab_run = st.tabs([
    "Überblick",
    "Dummys & missing Locos",
    "Lok-Zeitachse",
    "Fehlerqueue",
    "Exporte",
    "Pipeline"
])
'''
    new_tabs = '''tab_overview, tab_tasks, tab_timeline, tab_exports, tab_no_loco, tab_findings, tab_run = st.tabs([
    "1. Tagesprüfung",
    "2. Offene Aufgaben",
    "3. Lok prüfen",
    "4. Exporte erstellen",
    "⚙️ Technik: Loknummern",
    "⚙️ Technik: Regelqueue",
    "⚙️ Technik: Pipeline"
])
'''
    text = replace_once(text, old_tabs, new_tabs, "app Hauptnavigation")

    phase2_start = '''    # ==================================================
    # NETZENTGELT_QUALITY_GATE_PHASE2_V1_20260607: operative Betriebsampel und Export-Gate
    # ==================================================
'''
    phase2_end = '''    st.divider()

'''
    start_pos = text.find(phase2_start)
    if start_pos < 0:
        raise RuntimeError("Phase-2-Uebersichtsblock wurde nicht gefunden.")
    end_pos = text.find(phase2_end, start_pos)
    if end_pos < 0:
        raise RuntimeError("Ende des Phase-2-Uebersichtsblocks wurde nicht gefunden.")
    end_pos += len(phase2_end)

    replacement = '''    # ==================================================
    # NETZENTGELT_DAU_UX_PHASE3_V1_20260607: selbsterklaerende Tagespruefung
    # ==================================================
    render_operator_dashboard(
        export_gate=export_gate,
        global_export_blockers=global_export_blockers,
        excluded_export_rows=excluded_export_rows,
        findings=findings,
        operational_kpis=operational_kpis,
        reconciliation=reconciliation,
    )

    st.divider()

'''
    text = text[:start_pos] + replacement + text[end_pos:]

    task_block = '''with tab_tasks:
    render_open_tasks(
        export_gate=export_gate,
        global_export_blockers=global_export_blockers,
        findings=findings,
    )


'''
    text = replace_once(text, "with tab_no_loco:\n", task_block + "with tab_no_loco:\n", "app offene Aufgaben")

    replacements = [
        ('st.subheader("Überblick")', 'st.subheader("Tagesprüfung")'),
        ('"Neuen Import starten"', '"Daten aktualisieren und neu prüfen"'),
        ('st.metric("Errors", errors)', 'st.metric("Technische ERROR-Findings", errors)'),
        ('st.metric("Infos", infos)', 'st.metric("Technische INFO-Hinweise", infos)'),
        ('st.subheader("Dummys & missing Locos")', 'st.subheader("Technik: fehlende oder technische Loknummern")'),
        ('st.subheader("Lok-Zeitachse prüfen")', 'st.subheader("Lok im Detail prüfen")'),
        ('"IN_REPORT": "In Report"', '"IN_REPORT": "DE-relevant"'),
        ('"NOT_IN_REPORT": "Not in the Report"', '"NOT_IN_REPORT": "Außerhalb DE (nur Kontext)"'),
        ('"GAP": "GAP"', '"GAP": "Unterbrechung"'),
        ('"Report Scope"', '"Zeilen anzeigen"'),
        ('st.subheader("Fehler- und Prüfqueue")', 'st.subheader("Technik: vollständige Regelqueue")'),
    ]

    for old, new in replacements:
        if old in text:
            text = text.replace(old, new, 1)

    return text


def backup_files(paths: list[Path]) -> Path:
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = BACKUP_ROOT / f"netzentgelt_dau_ux_phase3_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)

    for path in paths:
        destination = backup_dir / path.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)

    if NEW_MODULE_TARGET.exists():
        destination = backup_dir / NEW_MODULE_TARGET.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(NEW_MODULE_TARGET, destination)

    LAST_BACKUP_FILE.write_text(str(backup_dir), encoding="utf-8")
    return backup_dir


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    for path in [APP_PATH, PHASE2_MODULE, PAYLOAD]:
        require_path(path)

    app_text, has_bom, newline_style = read_text_preserve_bom(APP_PATH)
    patched_app = patch_app(app_text)

    print("DAU-UX-Phase-3-Patch wurde gegen den lokalen Stand validiert.")
    print("Geplante Änderungen:")
    print("- app/app.py")
    print("- scripts/operator_ui_module.py")

    if args.dry_run:
        print("DRY RUN erfolgreich. Es wurden keine Dateien verändert.")
        return 0

    backup_dir = backup_files([APP_PATH])
    print(f"Backup erstellt: {backup_dir}")

    try:
        write_text_preserve_bom(APP_PATH, patched_app, has_bom, newline_style)
        shutil.copy2(PAYLOAD, NEW_MODULE_TARGET)
        py_compile.compile(str(APP_PATH), doraise=True)
        py_compile.compile(str(NEW_MODULE_TARGET), doraise=True)
    except Exception:
        print("Fehler beim Patchen. Stelle Backup automatisch wieder her.")
        source = backup_dir / APP_PATH.relative_to(ROOT)
        if source.exists():
            APP_PATH.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, APP_PATH)
        raise

    print("DAU-UX-Phase-3-Patch erfolgreich angewendet und syntaktisch validiert.")
    print("Nächster Schritt: 03_VALIDATE_DAU_UX_PHASE3.bat")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
