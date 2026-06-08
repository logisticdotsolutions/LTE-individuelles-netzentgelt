from __future__ import annotations

import argparse
import hashlib
import json
import py_compile
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

PHASE_ID = "NETZENTGELT_ATTRIBUTION_TIMEZONE_HOTFIX_V1_20260608"
MARKER = "NETZENTGELT_ATTRIBUTION_TIMEZONE_HOTFIX_V1_20260608"
EXPECTED_APP_GIT_BLOB_LF = "053bf45575e29c425b8366485ff4776717b6b71c"
TARGET = Path("app/app.py")
BACKUP_ROOT = Path(".netzentgelt_hotfix_backups")
LATEST_POINTER = BACKUP_ROOT / "attribution_timezone_hotfix_latest.txt"

HEADER_ANCHOR = '''st.title("🚆 Bahnstrom Deutschland - Tagesprüfung")
st.caption(
    "Operative Prüfung und Exportvorbereitung für das individuelle Netzentgelt. "
    "Technische Details sind bewusst nachrangig eingeordnet."
)
'''

HEADER_REPLACEMENT = HEADER_ANCHOR + '''
# NETZENTGELT_ATTRIBUTION_TIMEZONE_HOTFIX_V1_20260608
st.markdown(
    """
    <div style="margin-top: 0.35rem; margin-bottom: 0.85rem; padding: 0.65rem 0.85rem; border-left: 4px solid #4f81bd; background: rgba(79, 129, 189, 0.08); border-radius: 0.25rem;">
        <strong>Konzeption, Fachlogik &amp; Umsetzung: Christoph Orgl</strong><br>
        <span style="font-size: 0.88rem; opacity: 0.85;">LTE-group · KI-gestützte Entwicklung mit OpenAI ChatGPT als Engineering-Copilot</span>
    </div>
    """,
    unsafe_allow_html=True,
)
'''

SIDEBAR_ANCHOR = '''file_status_box()

timeline_path = EXPORT_DIR / "core_loco_timeline.csv"
'''

SIDEBAR_REPLACEMENT = '''file_status_box()

with st.sidebar.expander("Über dieses Tool", expanded=False):
    st.markdown("**Konzeption, Fachlogik & Umsetzung**")
    st.write("Christoph Orgl · LTE-group")
    st.caption("KI-gestützte Entwicklung mit OpenAI ChatGPT als Engineering-Copilot.")
    st.caption("MVP für die operative Prüfung und Exportvorbereitung im individuellen Netzentgelt.")

timeline_path = EXPORT_DIR / "core_loco_timeline.csv"
'''

IMPORT_TIME_ANCHOR = '''        last_import = get_last_raw_import_datetime()

        if last_import:
            st.markdown(
                f"### Letzter Import am "
                f"{last_import:%d.%m.%Y} "
                f"um {last_import:%H:%M}"
            )
'''

IMPORT_TIME_REPLACEMENT = '''        last_import_utc = get_last_raw_import_datetime()
        last_import_local = last_import_utc.astimezone() if last_import_utc else None

        if last_import_local:
            st.markdown(
                f"### Letzter Import am "
                f"{last_import_local:%d.%m.%Y} "
                f"um {last_import_local:%H:%M}"
            )
            st.caption("Anzeige in lokaler Systemzeit.")
'''


def _git_blob_sha(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("utf-8")
    return hashlib.sha1(header + data).hexdigest()


def _lf_bytes(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _detect_newline(data: bytes) -> str:
    return "\r\n" if b"\r\n" in data else "\n"


def _read_text(path: Path) -> tuple[str, str, bytes]:
    raw = path.read_bytes()
    newline = _detect_newline(raw)
    text = _lf_bytes(raw).decode("utf-8")
    return text, newline, raw


def _write_text(path: Path, text_lf: str, newline: str) -> None:
    rendered = text_lf if newline == "\n" else text_lf.replace("\n", "\r\n")
    path.write_bytes(rendered.encode("utf-8"))


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"Patchstelle '{label}' nicht eindeutig gefunden. Erwartet: 1, gefunden: {count}. Lokalen Stand prüfen."
        )
    return text.replace(old, new, 1)


def _project_root(cli_value: str | None) -> Path:
    if cli_value:
        return Path(cli_value).resolve()
    return Path(__file__).resolve().parent


def _validate_base(raw: bytes) -> None:
    actual_raw = _git_blob_sha(raw)
    actual_lf = _git_blob_sha(_lf_bytes(raw))
    if actual_lf != EXPECTED_APP_GIT_BLOB_LF:
        raise RuntimeError(
            "Lokaler Stand von 'app/app.py' weicht vom geprüften GitHub-Stand ab. "
            f"Erwarteter Git-Blob: {EXPECTED_APP_GIT_BLOB_LF}, lokal: {actual_raw}, LF-normalisiert: {actual_lf}. "
            "Bitte zuerst git status prüfen."
        )


def _patched_text(text: str) -> str:
    if MARKER in text:
        return text
    text = _replace_once(text, HEADER_ANCHOR, HEADER_REPLACEMENT, "sichtbarer Lösungsstempel im Kopfbereich")
    text = _replace_once(text, SIDEBAR_ANCHOR, SIDEBAR_REPLACEMENT, "Seitenleistenbereich Über dieses Tool")
    text = _replace_once(text, IMPORT_TIME_ANCHOR, IMPORT_TIME_REPLACEMENT, "Importzeitpunkt in lokaler Systemzeit")
    return text


def _compile(path: Path) -> None:
    py_compile.compile(str(path), doraise=True)


def _create_backup(root: Path, target: Path, raw: bytes) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = root / BACKUP_ROOT / f"attribution_timezone_hotfix_{stamp}"
    backup_target = backup_dir / target
    backup_target.parent.mkdir(parents=True, exist_ok=True)
    backup_target.write_bytes(raw)
    manifest = {
        "phase_id": PHASE_ID,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "files": [{"relative": str(target).replace("\\", "/"), "existed": True, "git_blob_sha": _git_blob_sha(raw)}],
    }
    (backup_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    (root / BACKUP_ROOT).mkdir(parents=True, exist_ok=True)
    (root / LATEST_POINTER).write_text(str(backup_dir.relative_to(root)).replace("\\", "/"), encoding="utf-8")
    return backup_dir


def dry_run(root: Path) -> int:
    path = root / TARGET
    if not path.exists():
        raise RuntimeError(f"Datei fehlt: {TARGET}")
    text, newline, raw = _read_text(path)
    if MARKER in text:
        print("OK: Lösungsstempel und lokale Zeitanzeige sind bereits installiert. Keine Änderungen erforderlich.")
        _compile(path)
        return 0
    _validate_base(raw)
    patched = _patched_text(text)
    tmp = root / ".attribution_timezone_hotfix_dry_run_app.py"
    try:
        _write_text(tmp, patched, newline)
        _compile(tmp)
    finally:
        if tmp.exists():
            tmp.unlink()
        pycache = tmp.parent / "__pycache__"
        if pycache.exists():
            shutil.rmtree(pycache, ignore_errors=True)
    print("OK: Dry Run erfolgreich. Lösungsstempel und lokale Zeitanzeige können sicher installiert werden.")
    print(f"OK: Zeilenumbruch bleibt erhalten: {'Windows-CRLF' if newline == chr(13)+chr(10) else 'LF'}")
    return 0


def apply(root: Path) -> int:
    path = root / TARGET
    if not path.exists():
        raise RuntimeError(f"Datei fehlt: {TARGET}")
    text, newline, raw = _read_text(path)
    if MARKER in text:
        print("OK: Lösungsstempel und lokale Zeitanzeige sind bereits installiert. Keine Änderungen erforderlich.")
        _compile(path)
        return 0
    _validate_base(raw)
    patched = _patched_text(text)
    backup_dir = _create_backup(root, TARGET, raw)
    _write_text(path, patched, newline)
    try:
        _compile(path)
    except Exception:
        path.write_bytes(raw)
        raise
    print(f"OK: Hotfix installiert. Backup: {backup_dir.relative_to(root)}")
    print(f"OK: Zeilenumbruch erhalten: {'Windows-CRLF' if newline == chr(13)+chr(10) else 'LF'}")
    return 0


def verify(root: Path) -> int:
    path = root / TARGET
    if not path.exists():
        raise RuntimeError(f"Datei fehlt: {TARGET}")
    text, _, _ = _read_text(path)
    required = [
        MARKER,
        "Konzeption, Fachlogik &amp; Umsetzung: Christoph Orgl",
        'with st.sidebar.expander("Über dieses Tool", expanded=False):',
        "OpenAI ChatGPT als Engineering-Copilot",
        "last_import_local = last_import_utc.astimezone() if last_import_utc else None",
        'st.caption("Anzeige in lokaler Systemzeit.")',
    ]
    missing = [item for item in required if item not in text]
    if missing:
        raise RuntimeError("Hotfix unvollständig. Fehlende Marker: " + " | ".join(missing))
    _compile(path)
    print("OK: Lösungsstempel vollständig vorhanden.")
    print("OK: Importzeitpunkt wird in lokaler Systemzeit angezeigt.")
    print("OK: Python-Syntaxprüfung erfolgreich.")
    return 0


def rollback(root: Path) -> int:
    pointer = root / LATEST_POINTER
    if not pointer.exists():
        raise RuntimeError("Kein Backup-Zeiger gefunden. Rollback nicht möglich.")
    backup_dir = root / pointer.read_text(encoding="utf-8").strip()
    backup_target = backup_dir / TARGET
    if not backup_target.exists():
        raise RuntimeError(f"Backup-Datei fehlt: {backup_target}")
    target = root / TARGET
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(backup_target.read_bytes())
    _compile(target)
    print(f"OK: Rollback aus {backup_dir.relative_to(root)} erfolgreich.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["dry-run", "apply", "verify", "rollback"])
    parser.add_argument("--project-root", default=None)
    args = parser.parse_args()
    root = _project_root(args.project_root)
    try:
        return {"dry-run": dry_run, "apply": apply, "verify": verify, "rollback": rollback}[args.mode](root)
    except Exception as exc:
        print(f"FEHLER: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
