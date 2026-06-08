from __future__ import annotations

import argparse
import hashlib
import json
import os
import py_compile
import shutil
from datetime import datetime, timezone
from pathlib import Path

PHASE_ID = "NETZENTGELT_QG_ACTUAL_OVERLAP_HOTFIX_V1_20260608"
MARKER = "NETZENTGELT_QG_ACTUAL_OVERLAP_HOTFIX_V1_20260608"
TARGET = Path("scripts/quality_gate_module.py")
EXPECTED_TARGET_GIT_BLOB_LF = "fdab431819584abf876c297d7da80079c93d2d7c"
BACKUP_ROOT = Path(".netzentgelt_hotfix_backups")
LATEST_POINTER = BACKUP_ROOT / "qg_actual_overlap_hotfix_latest.txt"

OLD_BLOCK = '''    con.execute(
        """
        create or replace temp table tmp_qg_day_overlap as
        with duplicate_slots as (
            select
                loco_no,
                coverage_date,
                slot_start_utc
            from tmp_qg_movement_slots
            group by loco_no, coverage_date, slot_start_utc
            having count(distinct source_table || ':' || cast(source_row_id as varchar)) > 1
        )
        select
            loco_no,
            coverage_date,
            count(*) as overlap_slot_count
        from duplicate_slots
        group by loco_no, coverage_date
        """
    )
'''

NEW_BLOCK = '''    # NETZENTGELT_QG_ACTUAL_OVERLAP_HOTFIX_V1_20260608
    # Überschneidungen dürfen nicht allein daraus abgeleitet werden, dass zwei
    # Bewegungen denselben 15-Minuten-Slot berühren. Direkt aneinandergrenzende
    # Intervalle sind fachlich zulässig. Deshalb werden zuerst echte zeitliche
    # Schnittmengen gebildet und erst danach auf 15-Minuten-Slots verdichtet.
    con.execute(
        """
        create or replace temp table tmp_qg_day_overlap as
        with movement_intervals as (
            select
                row_number() over () as overlap_row_no,
                loco_no,
                period_start_utc,
                period_end_utc
            from core_loco_timeline
            where row_type = 'MOVEMENT'
              and report_scope = 'IN_REPORT'
              and nullif(trim(loco_no), '') is not null
              and period_start_utc is not null
              and period_end_utc is not null
              and period_end_utc > period_start_utc
        ),
        actual_overlap_intervals as (
            select
                a.loco_no,
                greatest(a.period_start_utc, b.period_start_utc) as overlap_start_utc,
                least(a.period_end_utc, b.period_end_utc) as overlap_end_utc
            from movement_intervals a
            join movement_intervals b
              on b.loco_no = a.loco_no
             and b.overlap_row_no > a.overlap_row_no
             and a.period_start_utc < b.period_end_utc
             and b.period_start_utc < a.period_end_utc
        ),
        duplicate_slots as (
            select distinct
                o.loco_no,
                cast(slots.slot_start_utc as date) as coverage_date,
                slots.slot_start_utc
            from actual_overlap_intervals o
            cross join unnest(
                generate_series(
                    date_trunc('hour', o.overlap_start_utc)
                        + cast(floor(date_part('minute', o.overlap_start_utc) / 15) as bigint)
                          * interval '15 minutes',
                    o.overlap_end_utc - interval '1 microsecond',
                    interval '15 minutes'
                )
            ) as slots(slot_start_utc)
            where o.overlap_end_utc > o.overlap_start_utc
        )
        select
            loco_no,
            coverage_date,
            count(*) as overlap_slot_count
        from duplicate_slots
        group by loco_no, coverage_date
        """
    )
'''


def _git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("utf-8") + data).hexdigest()


def _lf_bytes(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _detect_newline(data: bytes) -> str:
    return "\r\n" if b"\r\n" in data else "\n"


def _read_text(path: Path) -> tuple[str, str, bytes]:
    raw = path.read_bytes()
    return _lf_bytes(raw).decode("utf-8-sig"), _detect_newline(raw), raw


def _write_text(path: Path, text_lf: str, newline: str) -> None:
    rendered = text_lf if newline == "\n" else text_lf.replace("\n", "\r\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(rendered.encode("utf-8"))


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"Patchstelle '{label}' nicht eindeutig gefunden. Erwartet: 1, gefunden: {count}. Lokalen Stand prüfen."
        )
    return text.replace(old, new, 1)


def _project_root(cli_value: str | None) -> Path:
    return Path(cli_value).resolve() if cli_value else Path(__file__).resolve().parent


def _validate_base(raw: bytes) -> None:
    if os.environ.get("NETZENTGELT_ALLOW_QG_FIXTURE") == "1":
        return
    actual_raw = _git_blob_sha(raw)
    actual_lf = _git_blob_sha(_lf_bytes(raw))
    if actual_lf != EXPECTED_TARGET_GIT_BLOB_LF:
        raise RuntimeError(
            "Lokaler Stand von 'scripts/quality_gate_module.py' weicht vom geprüften GitHub-Stand ab. "
            f"Erwarteter Git-Blob: {EXPECTED_TARGET_GIT_BLOB_LF}, lokal: {actual_raw}, LF-normalisiert: {actual_lf}. "
            "Bitte zuerst git status prüfen."
        )


def _patched_text(text: str) -> str:
    if MARKER in text:
        return text
    return _replace_once(text, OLD_BLOCK, NEW_BLOCK, "Quality Gate tatsächliche Überschneidungen")


def _compile(path: Path) -> None:
    py_compile.compile(str(path), doraise=True)


def _create_backup(root: Path, target: Path, raw: bytes) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = root / BACKUP_ROOT / f"qg_actual_overlap_hotfix_{stamp}"
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
        print("OK: Quality-Gate-Overlap-Hotfix ist bereits installiert. Keine Änderungen erforderlich.")
        _compile(path)
        return 0
    _validate_base(raw)
    patched = _patched_text(text)
    tmp = root / ".qg_actual_overlap_hotfix_dry_run.py"
    try:
        _write_text(tmp, patched, newline)
        _compile(tmp)
    finally:
        if tmp.exists():
            tmp.unlink()
        shutil.rmtree(root / "__pycache__", ignore_errors=True)
    print("OK: Dry Run erfolgreich. Quality-Gate-Overlap-Hotfix kann sicher installiert werden.")
    print(f"OK: Zeilenumbruch bleibt erhalten: {'Windows-CRLF' if newline == chr(13)+chr(10) else 'LF'}")
    return 0


def apply(root: Path) -> int:
    path = root / TARGET
    if not path.exists():
        raise RuntimeError(f"Datei fehlt: {TARGET}")
    text, newline, raw = _read_text(path)
    if MARKER in text:
        print("OK: Quality-Gate-Overlap-Hotfix ist bereits installiert. Keine Änderungen erforderlich.")
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
    print(f"OK: Quality-Gate-Overlap-Hotfix installiert. Backup: {backup_dir.relative_to(root)}")
    print(f"OK: Zeilenumbruch erhalten: {'Windows-CRLF' if newline == chr(13)+chr(10) else 'LF'}")
    return 0


def verify(root: Path) -> int:
    path = root / TARGET
    text, _, _ = _read_text(path)
    required = [
        MARKER,
        "actual_overlap_intervals as (",
        "a.period_start_utc < b.period_end_utc",
        "b.period_start_utc < a.period_end_utc",
        "o.overlap_end_utc - interval '1 microsecond'",
    ]
    missing = [item for item in required if item not in text]
    if missing:
        raise RuntimeError("Hotfix unvollständig. Fehlende Marker: " + " | ".join(missing))
    _compile(path)
    print("OK: Quality-Gate-Overlap-Hotfix vollständig vorhanden.")
    print("OK: Direkt aneinandergrenzende Bewegungen werden nicht mehr als Überschneidung bewertet.")
    print("OK: Python-Syntaxprüfung erfolgreich.")
    return 0


def rollback(root: Path) -> int:
    pointer = root / LATEST_POINTER
    if not pointer.exists():
        raise RuntimeError("Kein Hotfix-Backup gefunden. Rollback kann nicht ausgeführt werden.")
    backup_dir = root / pointer.read_text(encoding="utf-8").strip()
    backup_target = backup_dir / TARGET
    if not backup_target.exists():
        raise RuntimeError(f"Backup-Datei fehlt: {backup_target}")
    target = root / TARGET
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(backup_target, target)
    _compile(target)
    print(f"OK: Code-Rollback abgeschlossen. Wiederhergestellt aus: {backup_dir.relative_to(root)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["dry-run", "apply", "verify", "rollback"])
    parser.add_argument("--project-root")
    args = parser.parse_args()
    root = _project_root(args.project_root)
    try:
        return globals()[args.action.replace("-", "_")](root)
    except Exception as exc:
        print(f"FEHLER: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
