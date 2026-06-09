from __future__ import annotations

from pathlib import Path
import datetime
import hashlib
import json
import py_compile
import sys

MARKER = "NETZENTGELT_DUMMY_LOCOMOTIVE_HARDENING_V1_20260608"
ROOT = Path(__file__).resolve().parent
PAYLOAD = ROOT / "payload"
BACKUP_ROOT = ROOT / ".dummy_locomotive_hardening_backups"
MODIFIED = {
    Path("scripts/run_all.py"): "49f0088dc3959fc25d8417a3c33436745dc45a4a",
    Path("scripts/manual_override_ui_module.py"): "1d26780f7c4be4c49382a69770566b45c0af5871",
}
NEW_FILES = [
    Path("scripts/dummy_locomotive_module.py"),
    Path("scripts/verify_dummy_locomotive_hardening.py"),
    Path("scripts/test_dummy_locomotive_hardening.py"),
    Path("data/01_mapping/dummy_locomotives.csv"),
]


def lf_bytes(raw: bytes) -> bytes:
    return raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def git_blob_sha(raw: bytes) -> str:
    data = lf_bytes(raw)
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def read_text(path: Path) -> str:
    return lf_bytes(path.read_bytes()).decode("utf-8")


def crlf_bytes(text: str) -> bytes:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return normalized.replace("\n", "\r\n").encode("utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"Patchstelle '{label}' nicht eindeutig. Erwartet: 1, gefunden: {count}."
        )
    return text.replace(old, new, 1)


def patch_run_all(text: str) -> str:
    if MARKER in text:
        return text
    text = replace_once(
        text,
        """from rule_engine_hardening_phase6d import (
    finalize_quality_gate_phase6d,
    insert_gap_only_day_findings_phase6d,
)
""",
        """from rule_engine_hardening_phase6d import (
    finalize_quality_gate_phase6d,
    insert_gap_only_day_findings_phase6d,
)
# NETZENTGELT_DUMMY_LOCOMOTIVE_HARDENING_V1_20260608
from dummy_locomotive_module import (
    build_dummy_locomotive_catalog,
    consolidate_dummy_locomotive_findings,
    exclude_dummy_locomotives_from_staging,
)
""",
        "run_all imports",
    )
    text = replace_once(
        text,
        "        build_cancelled_transport_exclusions(con)\n",
        "        build_cancelled_transport_exclusions(con)\n        build_dummy_locomotive_catalog(con)\n",
        "run_all dummy catalog",
    )
    text = replace_once(
        text,
        "        build_loco_events(con)\n        apply_staging_manual_overrides(con, run_id)\n",
        "        build_loco_events(con)\n        exclude_dummy_locomotives_from_staging(con)\n        apply_staging_manual_overrides(con, run_id)\n",
        "run_all staging exclusion",
    )
    text = replace_once(
        text,
        "        build_findings(con, run_id, home_country_iso=HOME_COUNTRY_ISO)\n        harden_findings_and_export_policy(con, run_id)\n",
        "        build_findings(con, run_id, home_country_iso=HOME_COUNTRY_ISO)\n        consolidate_dummy_locomotive_findings(con, run_id)\n        harden_findings_and_export_policy(con, run_id)\n",
        "run_all R012 consolidation",
    )
    text = replace_once(
        text,
        '            ("audit_excluded_cancelled_transports", "audit_excluded_cancelled_transports.csv"),\n',
        '            ("audit_excluded_cancelled_transports", "audit_excluded_cancelled_transports.csv"),\n'
        '            ("cfg_dummy_locomotives_effective", "cfg_dummy_locomotives_effective.csv"),\n'
        '            ("audit_excluded_dummy_locomotives", "audit_excluded_dummy_locomotives.csv"),\n'
        '            ("audit_excluded_dummy_locomotive_staging", "audit_excluded_dummy_locomotive_staging.csv"),\n',
        "run_all audit exports",
    )
    return text


def patch_manual_ui(text: str) -> str:
    if MARKER in text:
        return text
    old = """    cases = _build_case_table(findings=findings, timeline=timeline)
    if prefill:
        cases = pd.concat([pd.DataFrame([_prefill_case(prefill)]), cases], ignore_index=True)
        st.success(
"""
    new = """    cases = _build_case_table(findings=findings, timeline=timeline)
    # NETZENTGELT_DUMMY_LOCOMOTIVE_HARDENING_V1_20260608
    # Controller waehlen zuerst eine Lok. Danach erscheinen ausschliesslich deren
    # Prueffaelle. Dadurch rutschen keine GAP-Faelle anderer Loks in die Bearbeitung.
    free_label = "Freie manuelle Erfassung"
    case_loco_options = sorted({
        _clean(value) for value in cases.get("loco_no", pd.Series(dtype=str)).tolist()
        if _clean(value)
    })
    prefill_loco = _clean(prefill.get("loco_no"))
    filter_options = [free_label, *case_loco_options]
    default_filter_index = filter_options.index(prefill_loco) if prefill_loco in filter_options else 0
    selected_case_loco = st.selectbox(
        "Loknummer fuer Bearbeitung auswaehlen",
        filter_options,
        index=default_filter_index,
        key=f"manual_override_case_loco_filter_{prefill_loco or 'manual'}",
    )
    if selected_case_loco == free_label:
        cases = cases[cases["case_label"].eq(free_label)].copy()
    else:
        cases = cases[
            cases["case_label"].eq(free_label)
            | cases["loco_no"].fillna("").astype(str).eq(selected_case_loco)
        ].copy()
    if prefill:
        cases = pd.concat([pd.DataFrame([_prefill_case(prefill)]), cases], ignore_index=True)
        st.success(
"""
    return replace_once(text, old, new, "manual override loco filter")


PATCHERS = {
    Path("scripts/run_all.py"): patch_run_all,
    Path("scripts/manual_override_ui_module.py"): patch_manual_ui,
}


def validate(root: Path) -> None:
    for rel, expected_sha in MODIFIED.items():
        path = root / rel
        if not path.exists():
            raise RuntimeError(f"Datei fehlt: {rel}")
        text = read_text(path)
        if MARKER in text:
            continue
        actual_sha = git_blob_sha(path.read_bytes())
        if actual_sha != expected_sha:
            raise RuntimeError(
                f"Lokaler Stand von '{rel}' weicht vom geprueften GitHub-Stand ab. "
                f"Erwarteter Git-Blob: {expected_sha}, lokal: {actual_sha}."
            )
    for rel in NEW_FILES:
        target = root / rel
        source = PAYLOAD / rel
        if target.exists() and target.read_bytes() != source.read_bytes():
            raise RuntimeError(f"Neue Datei existiert bereits mit abweichendem Inhalt: {rel}")


def create_backup() -> Path:
    stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S_%f")
    backup = BACKUP_ROOT / stamp
    backup.mkdir(parents=True, exist_ok=True)
    return backup


def dry_run(root: Path) -> int:
    validate(root)
    for rel, patcher in PATCHERS.items():
        patcher(read_text(root / rel))
    print("OK: Dry Run erfolgreich. Keine Dateien wurden veraendert.")
    return 0


def apply(root: Path) -> int:
    validate(root)
    backup = create_backup()
    manifest = []
    for rel, patcher in PATCHERS.items():
        target = root / rel
        original = target.read_bytes()
        patched = patcher(read_text(target))
        backup_target = backup / rel
        backup_target.parent.mkdir(parents=True, exist_ok=True)
        backup_target.write_bytes(original)
        target.write_bytes(crlf_bytes(patched))
        manifest.append({"path": str(rel), "kind": "modified"})
    for rel in NEW_FILES:
        target = root / rel
        source = PAYLOAD / rel
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
            manifest.append({"path": str(rel), "kind": "new"})
    (backup / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (BACKUP_ROOT / "LATEST.txt").write_text(str(backup), encoding="utf-8")
    print(f"OK: Hotfix angewandt. Backup: {backup}")
    return 0


def verify(root: Path) -> int:
    for rel in MODIFIED:
        target = root / rel
        text = read_text(target)
        if MARKER not in text:
            raise RuntimeError(f"Marker fehlt: {rel}")
        if b"\r\n" not in target.read_bytes():
            raise RuntimeError(f"Windows-CRLF fehlt: {rel}")
    for rel in NEW_FILES:
        if not (root / rel).exists():
            raise RuntimeError(f"Neue Datei fehlt: {rel}")
    for rel in [
        *MODIFIED.keys(),
        Path("scripts/dummy_locomotive_module.py"),
        Path("scripts/verify_dummy_locomotive_hardening.py"),
        Path("scripts/test_dummy_locomotive_hardening.py"),
    ]:
        py_compile.compile(str(root / rel), doraise=True)
    print("OK: Marker, Dateien, CRLF und Python-Syntax verifiziert.")
    return 0


def rollback(root: Path) -> int:
    latest = BACKUP_ROOT / "LATEST.txt"
    if not latest.exists():
        raise RuntimeError("Kein Backup gefunden.")
    backup = Path(latest.read_text(encoding="utf-8").strip())
    manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    for item in manifest:
        rel = Path(item["path"])
        target = root / rel
        if item["kind"] == "modified":
            target.write_bytes((backup / rel).read_bytes())
        elif item["kind"] == "new" and target.exists():
            target.unlink()
    print(f"OK: Rollback aus {backup} erfolgreich.")
    return 0


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else "dry-run"
    handlers = {"dry-run": dry_run, "apply": apply, "verify": verify, "rollback": rollback}
    try:
        return handlers[command](ROOT)
    except Exception as exc:
        print(f"FEHLER: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
