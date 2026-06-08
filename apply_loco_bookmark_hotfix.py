from __future__ import annotations

import argparse
import hashlib
import json
import py_compile
import shutil
from datetime import datetime, timezone
from pathlib import Path

PHASE_ID = "NETZENTGELT_LOCO_BOOKMARK_HOTFIX_V1_20260608"
MARKER_OPERATOR = "NETZENTGELT_LOCO_BOOKMARK_HOTFIX_OPERATOR_V1_20260608"
MARKER_APP = "NETZENTGELT_LOCO_BOOKMARK_HOTFIX_APP_V1_20260608"

BACKUP_ROOT = Path(".netzentgelt_hotfix_backups")
LATEST_POINTER = BACKUP_ROOT / "loco_bookmark_hotfix_latest.txt"

FILES = {
    Path("scripts/operator_ui_module.py"): "f2ac4215fe54445a331ec6eb3edbd5d5916d3e2e",
    Path("app/app.py"): "9ab3194ec6e17cb6a9627239a74eaefdbe96ab77",
}

OPERATOR_ANCHOR = '''            st.session_state["timeline_preview_loco"] = selected_loco
            st.success(
                f"Lok {selected_loco} wurde vorgemerkt. Öffne jetzt den Tab '4. Lok prüfen'."
            )
'''

OPERATOR_REPLACEMENT = '''            # NETZENTGELT_LOCO_BOOKMARK_HOTFIX_OPERATOR_V1_20260608
            # Die verbleibende Detailansicht verwendet den Widget-Key
            # ``timeline_detail_loco``. Die separate Vormerkung bleibt für einen
            # sichtbaren Hinweis im Reiter "4. Lok prüfen" erhalten.
            st.session_state["timeline_detail_loco"] = selected_loco
            st.session_state["timeline_bookmarked_loco"] = selected_loco
            st.success(
                f"Lok {selected_loco} wurde vorgemerkt. Öffne jetzt den Tab '4. Lok prüfen'. "
                "Die Lok ist dort bereits ausgewählt."
            )
'''

APP_HEADER_ANCHOR = '''with tab_timeline:
    st.header("🔎 Lok-Detailprüfung")

    core_path = EXPORT_DIR / "core_loco_timeline.csv"
'''

APP_HEADER_REPLACEMENT = '''with tab_timeline:
    st.header("🔎 Lok-Detailprüfung")

    # NETZENTGELT_LOCO_BOOKMARK_HOTFIX_APP_V1_20260608
    bookmarked_loco = str(
        st.session_state.get("timeline_bookmarked_loco", "")
    ).strip()

    if bookmarked_loco:
        st.info(
            f"Vorgemerkte Lok: {bookmarked_loco}. "
            "Die Lok ist in der Auswahl unten bereits vorbelegt."
        )

    core_path = EXPORT_DIR / "core_loco_timeline.csv"
'''

APP_SELECT_ANCHOR = '''        selected_loco = st.selectbox(
            "Lok auswählen",
            loco_values,
            index=0 if loco_values else None,
            key="timeline_detail_loco",
        )
'''

APP_SELECT_REPLACEMENT = '''        # Falls der Arbeitszeitraum geändert wurde und die bisher ausgewählte
        # Lok darin nicht vorkommt, darf der Selectbox-State nicht auf einem
        # ungültigen Wert stehen bleiben.
        selected_loco_state = str(
            st.session_state.get("timeline_detail_loco", "")
        ).strip()

        if selected_loco_state and selected_loco_state not in loco_values:
            st.session_state.pop("timeline_detail_loco", None)

        selected_loco = st.selectbox(
            "Lok auswählen",
            loco_values,
            index=0 if loco_values else None,
            key="timeline_detail_loco",
        )
'''

def _git_blob_sha(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("utf-8")
    return hashlib.sha1(header + data).hexdigest()

def _lf_bytes(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")

def _detect_newline(data: bytes) -> str:
    return "\r\n" if b"\r\n" in data else "\n"

def _read(path: Path) -> tuple[str, str, bytes]:
    raw = path.read_bytes()
    newline = _detect_newline(raw)
    return _lf_bytes(raw).decode("utf-8"), newline, raw

def _write(path: Path, text_lf: str, newline: str) -> None:
    rendered = text_lf if newline == "\n" else text_lf.replace("\n", "\r\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(rendered.encode("utf-8"))

def _replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"Patchstelle '{label}' nicht eindeutig gefunden. Erwartet: 1, gefunden: {count}. "
            "Lokalen Stand prüfen."
        )
    return text.replace(old, new, 1)

def _validate_base(relative: Path, raw: bytes) -> None:
    expected = FILES[relative]
    actual_raw = _git_blob_sha(raw)
    actual_lf = _git_blob_sha(_lf_bytes(raw))
    if actual_lf != expected:
        raise RuntimeError(
            f"Lokaler Stand von '{relative.as_posix()}' weicht vom geprüften GitHub-Stand ab. "
            f"Erwarteter Git-Blob: {expected}, lokal: {actual_raw}, LF-normalisiert: {actual_lf}. "
            "Bitte zuerst git status prüfen."
        )

def _patch_operator(text: str) -> str:
    if MARKER_OPERATOR in text:
        return text
    return _replace_once(
        text, OPERATOR_ANCHOR, OPERATOR_REPLACEMENT,
        "korrekter Widget-Key für vorgemerkte Lok",
    )

def _patch_app(text: str) -> str:
    if MARKER_APP in text:
        return text
    text = _replace_once(
        text, APP_HEADER_ANCHOR, APP_HEADER_REPLACEMENT,
        "sichtbarer Hinweis auf vorgemerkte Lok",
    )
    text = _replace_once(
        text, APP_SELECT_ANCHOR, APP_SELECT_REPLACEMENT,
        "defensive Lok-Auswahl nach Zeitraumwechsel",
    )
    return text

def _patched(relative: Path, text: str) -> str:
    return _patch_operator(text) if relative.as_posix() == "scripts/operator_ui_module.py" else _patch_app(text)

def _compile(path: Path) -> None:
    py_compile.compile(str(path), doraise=True)

def _root(cli: str | None) -> Path:
    return Path(cli).resolve() if cli else Path(__file__).resolve().parent

def _installed(root: Path) -> bool:
    operator = root / "scripts/operator_ui_module.py"
    app = root / "app/app.py"
    return (
        operator.exists() and app.exists()
        and MARKER_OPERATOR in operator.read_text(encoding="utf-8")
        and MARKER_APP in app.read_text(encoding="utf-8")
    )

def _backup(root: Path, originals: dict[Path, bytes]) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = root / BACKUP_ROOT / f"loco_bookmark_hotfix_{stamp}"
    for relative, raw in originals.items():
        target = backup_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    manifest = {
        "phase_id": PHASE_ID,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "files": [
            {"relative": relative.as_posix(), "existed": True, "git_blob_sha": _git_blob_sha(raw)}
            for relative, raw in originals.items()
        ],
    }
    (backup_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    (root / BACKUP_ROOT).mkdir(parents=True, exist_ok=True)
    (root / LATEST_POINTER).write_text(backup_dir.relative_to(root).as_posix(), encoding="utf-8")
    return backup_dir

def verify(root: Path) -> int:
    operator = (root / "scripts/operator_ui_module.py").read_text(encoding="utf-8")
    app = (root / "app/app.py").read_text(encoding="utf-8")
    required = [
        (operator, MARKER_OPERATOR),
        (operator, 'st.session_state["timeline_detail_loco"] = selected_loco'),
        (operator, 'st.session_state["timeline_bookmarked_loco"] = selected_loco'),
        (operator, "Öffne jetzt den Tab '4. Lok prüfen'"),
        (app, MARKER_APP),
        (app, 'st.session_state.get("timeline_bookmarked_loco", "")'),
        (app, "Vorgemerkte Lok:"),
        (app, 'st.session_state.pop("timeline_detail_loco", None)'),
    ]
    missing = [needle for text, needle in required if needle not in text]
    if missing:
        raise RuntimeError("Hotfix unvollständig. Fehlende Marker: " + " | ".join(missing))
    _compile(root / "scripts/operator_ui_module.py")
    _compile(root / "app/app.py")
    print("OK: Vormerkung verwendet den sichtbaren Lok-Auswahl-Key.")
    print("OK: Tab-Verweis zeigt auf '4. Lok prüfen'.")
    print("OK: Sichtbarer Hinweis auf die vorgemerkte Lok vorhanden.")
    print("OK: Python-Syntaxprüfung erfolgreich.")
    return 0

def dry_run(root: Path) -> int:
    if _installed(root):
        verify(root)
        print("OK: Hotfix ist bereits installiert. Keine Änderungen erforderlich.")
        return 0
    for relative in FILES:
        path = root / relative
        if not path.exists():
            raise RuntimeError(f"Datei fehlt: {relative.as_posix()}")
        text, newline, raw = _read(path)
        _validate_base(relative, raw)
        patched = _patched(relative, text)
        temp = root / f".loco_bookmark_dry_run_{relative.name}"
        try:
            _write(temp, patched, newline)
            _compile(temp)
        finally:
            if temp.exists():
                temp.unlink()
    cache = root / "__pycache__"
    if cache.exists():
        shutil.rmtree(cache, ignore_errors=True)
    print("OK: Dry Run erfolgreich. Keine Dateien wurden verändert.")
    return 0

def apply(root: Path) -> int:
    if _installed(root):
        verify(root)
        print("OK: Hotfix ist bereits installiert. Keine Änderungen erforderlich.")
        return 0
    originals: dict[Path, bytes] = {}
    rendered: dict[Path, tuple[str, str]] = {}
    for relative in FILES:
        path = root / relative
        if not path.exists():
            raise RuntimeError(f"Datei fehlt: {relative.as_posix()}")
        text, newline, raw = _read(path)
        _validate_base(relative, raw)
        originals[relative] = raw
        rendered[relative] = (_patched(relative, text), newline)
    backup_dir = _backup(root, originals)
    try:
        for relative, (text, newline) in rendered.items():
            _write(root / relative, text, newline)
            _compile(root / relative)
    except Exception:
        for relative, raw in originals.items():
            (root / relative).write_bytes(raw)
        raise
    print(f"OK: Hotfix installiert. Backup: {backup_dir.relative_to(root)}")
    return 0

def rollback(root: Path) -> int:
    pointer = root / LATEST_POINTER
    if not pointer.exists():
        raise RuntimeError("Kein Backup-Zeiger gefunden. Rollback nicht möglich.")
    backup_dir = root / pointer.read_text(encoding="utf-8").strip()
    manifest = json.loads((backup_dir / "manifest.json").read_text(encoding="utf-8"))
    for item in manifest["files"]:
        relative = Path(item["relative"])
        source = backup_dir / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    print(f"OK: Rollback abgeschlossen. Wiederhergestellt aus: {backup_dir.relative_to(root)}")
    return 0

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["dry-run", "apply", "verify", "rollback"])
    parser.add_argument("--project-root")
    args = parser.parse_args()
    try:
        return {"dry-run": dry_run, "apply": apply, "verify": verify, "rollback": rollback}[args.command](_root(args.project_root))
    except Exception as exc:
        print(f"FEHLER: {exc}")
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
