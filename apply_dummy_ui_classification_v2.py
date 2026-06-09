from __future__ import annotations

import argparse
import hashlib
import json
import py_compile
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKUP_ROOT = ROOT / ".dummy_ui_classification_v2_backups"
MANIFEST_NAME = "manifest.json"
MARKER = "NETZENTGELT_DUMMY_UI_CLASSIFICATION_V2_20260609"
HISTORICAL_TEST_MARKER = "NETZENTGELT_HISTORICAL_INSTALLER_TEST_SKIP_V1_20260609"

# GitHub main 06b05d20bc3b093abbc6559c5ed6f43285a8018e
EXPECTED_BLOB_SHA = {
    "scripts/dummy_locomotive_module.py": "39c98089e0ebe294ea539b5dd34c59e9ba267f8f",
    "scripts/manual_override_ui_module.py": "da3fa7f142cfdad45361e987fafe9b5630fbf0cf",
    "data/01_mapping/dummy_locomotives.csv": "f854f9175247b0261bf0f7d5f6665dc318fb2dad",
    "tests/test_installer_phase6b.py": "7d917f6ec8d8195c763984c02c3cac29e2fa7301",
    "tests/test_installer_phase6c.py": "10d88702c0af7c15bc74c35608347ea210868c32",
}

NEW_FILES = {
    "scripts/test_dummy_locomotive_ui_classification.py": "payload/scripts/test_dummy_locomotive_ui_classification.py",
    "scripts/verify_dummy_locomotive_ui_classification.py": "payload/scripts/verify_dummy_locomotive_ui_classification.py",
}


def git_blob_sha(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def normalize_lf(raw: bytes) -> bytes:
    return raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def accepted_sha(raw: bytes, expected: str) -> bool:
    return git_blob_sha(raw) == expected or git_blob_sha(normalize_lf(raw)) == expected


def decode_text(raw: bytes) -> tuple[str, bool, str]:
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    newline = "\r\n" if b"\r\n" in raw else "\n"
    return text.replace("\r\n", "\n").replace("\r", "\n"), has_bom, newline


def encode_text(text: str, has_bom: bool, newline: str) -> bytes:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    raw = normalized.replace("\n", newline).encode("utf-8")
    return (b"\xef\xbb\xbf" + raw) if has_bom else raw


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Patchstelle '{label}' nicht eindeutig gefunden. Erwartet: 1, gefunden: {count}.")
    return text.replace(old, new, 1)


def patch_dummy_module(text: str) -> str:
    if MARKER in text:
        return text
    text = replace_once(
        text,
        "import csv\nfrom pathlib import Path\nfrom typing import Iterable\n",
        "import csv\nimport os\nimport shutil\nfrom datetime import datetime, timezone\nfrom pathlib import Path\nfrom typing import Iterable\n",
        "dummy module imports",
    )
    text = replace_once(
        text,
        'DUMMY_MAPPING_PATH = ROOT / "data" / "01_mapping" / "dummy_locomotives.csv"\nMARKER = "NETZENTGELT_DUMMY_LOCOMOTIVE_HARDENING_V1_20260608"\n',
        'DUMMY_MAPPING_PATH = ROOT / "data" / "01_mapping" / "dummy_locomotives.csv"\nDUMMY_CHANGE_LOG_PATH = ROOT / "data" / "01_mapping" / "dummy_locomotive_change_log.csv"\nDUMMY_MAPPING_BACKUP_DIR = ROOT / ".dummy_locomotive_mapping_backups"\nDUMMY_MAPPING_COLUMNS = ("loco_no", "reason", "active_flag")\nDUMMY_CHANGE_LOG_COLUMNS = ("changed_at_utc", "action", "loco_no", "reason", "changed_by")\nMARKER = "NETZENTGELT_DUMMY_LOCOMOTIVE_HARDENING_V1_20260608"\nDUMMY_UI_CLASSIFICATION_MARKER = "NETZENTGELT_DUMMY_UI_CLASSIFICATION_V2_20260609"\n',
        "dummy module constants",
    )
    if '    "91806189000-3",\n' not in text:
        text = replace_once(
            text,
            '    "00000000001-8",\n)\n',
            '    "00000000001-8",\n    "91806189000-3",\n)\n',
            "add known dummy locomotive",
        )
    helper = r'''

def _utc_now_text() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_all_mapping_rows() -> list[dict[str, str]]:
    _ensure_mapping_csv()
    rows: list[dict[str, str]] = []
    with DUMMY_MAPPING_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        for row in reader:
            loco_no = str(row.get("loco_no") or "").strip()
            if not loco_no:
                continue
            rows.append(
                {
                    "loco_no": loco_no,
                    "reason": str(row.get("reason") or "Bekannte Planungs-/Dummy-Loknummer").strip(),
                    "active_flag": str(row.get("active_flag") or "Y").strip().upper() or "Y",
                }
            )
    return rows


def _backup_mapping_csv() -> Path | None:
    if not DUMMY_MAPPING_PATH.exists():
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_%f")
    target_dir = DUMMY_MAPPING_BACKUP_DIR / stamp
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / DUMMY_MAPPING_PATH.name
    shutil.copy2(DUMMY_MAPPING_PATH, target)
    return target


def _write_mapping_rows_atomic(rows: list[dict[str, str]]) -> None:
    DUMMY_MAPPING_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = DUMMY_MAPPING_PATH.with_name(DUMMY_MAPPING_PATH.name + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(DUMMY_MAPPING_COLUMNS), delimiter=";", lineterminator="\r\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: str(row.get(column) or "").strip() for column in DUMMY_MAPPING_COLUMNS})
    os.replace(temporary, DUMMY_MAPPING_PATH)


def _append_dummy_change_log(*, action: str, loco_no: str, reason: str, changed_by: str) -> None:
    DUMMY_CHANGE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    exists = DUMMY_CHANGE_LOG_PATH.exists()
    with DUMMY_CHANGE_LOG_PATH.open("a", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(DUMMY_CHANGE_LOG_COLUMNS), delimiter=";", lineterminator="\r\n")
        if not exists:
            writer.writeheader()
        writer.writerow(
            {
                "changed_at_utc": _utc_now_text(),
                "action": action,
                "loco_no": loco_no,
                "reason": reason,
                "changed_by": changed_by,
            }
        )


def upsert_dummy_locomotive_mapping(*, loco_no: str, reason: str, changed_by: str) -> str:
    """Controller-Klassifikation auditierbar in den zentralen Dummy-Katalog uebernehmen."""
    cleaned_loco = str(loco_no or "").strip()
    cleaned_reason = str(reason or "").strip()
    cleaned_by = str(changed_by or "").strip() or "unknown"
    if not cleaned_loco:
        raise ValueError("Bitte eine Loknummer angeben.")
    if not cleaned_reason:
        raise ValueError("Bitte eine nachvollziehbare Begruendung angeben.")

    rows = _read_all_mapping_rows()
    result: list[dict[str, str]] = []
    found = False
    changed = False
    action = "CREATE"
    for row in rows:
        if row["loco_no"] != cleaned_loco:
            result.append(row)
            continue
        if found:
            changed = True
            continue
        found = True
        old_active = row.get("active_flag", "Y").strip().upper() or "Y"
        old_reason = row.get("reason", "").strip()
        if old_active in {"N", "NO", "FALSE", "0"}:
            action = "REACTIVATE"
            changed = True
        elif old_reason != cleaned_reason:
            action = "UPDATE_REASON"
            changed = True
        else:
            action = "ALREADY_ACTIVE"
        result.append({"loco_no": cleaned_loco, "reason": cleaned_reason, "active_flag": "Y"})
    if not found:
        result.append({"loco_no": cleaned_loco, "reason": cleaned_reason, "active_flag": "Y"})
        changed = True

    if changed:
        _backup_mapping_csv()
        _write_mapping_rows_atomic(result)
    _append_dummy_change_log(action=action, loco_no=cleaned_loco, reason=cleaned_reason, changed_by=cleaned_by)
    return action
'''.lstrip("\n")
    text = replace_once(
        text,
        "\ndef _read_mapping_rows() -> list[dict[str, str]]:\n",
        "\n" + helper + "\ndef _read_mapping_rows() -> list[dict[str, str]]:\n",
        "dummy mapping upsert helpers",
    )
    return text


def patch_manual_ui(text: str) -> str:
    if MARKER in text:
        return text
    text = replace_once(
        text,
        "from manual_override_batch_module import (\n    PHASE5D_BATCH_MARKER,\n    create_overrides_from_selected_suggestions,\n)\n",
        "from manual_override_batch_module import (\n    PHASE5D_BATCH_MARKER,\n    create_overrides_from_selected_suggestions,\n)\nfrom dummy_locomotive_module import (\n    DUMMY_CHANGE_LOG_COLUMNS,\n    DUMMY_CHANGE_LOG_PATH,\n    upsert_dummy_locomotive_mapping,\n)\n",
        "manual ui dummy imports",
    )
    text = replace_once(
        text,
        'PHASE5D_UI_MARKER = "NETZENTGELT_MANUAL_OVERRIDE_PHASE5D_V1_20260608"\n',
        'PHASE5D_UI_MARKER = "NETZENTGELT_MANUAL_OVERRIDE_PHASE5D_V1_20260608"\nDUMMY_UI_CLASSIFICATION_MARKER = "NETZENTGELT_DUMMY_UI_CLASSIFICATION_V2_20260609"\n',
        "manual ui marker",
    )
    text = replace_once(
        text,
        '    "CASE_NOTE": "Bearbeitungsnotiz hinterlegen",\n',
        '    "CASE_NOTE": "Bearbeitungsnotiz hinterlegen",\n    "MARK_DUMMY_LOCOMOTIVE": "Als Dummy-/Planungslok markieren",\n',
        "manual ui dummy action label",
    )
    text = replace_once(
        text,
        '    form_key = f"manual_override_form_{override_type}_{abs(hash(selected_label))}_{_clean(prefill.get(\'suggestion_id\'))}"\n',
        '    is_dummy_action = override_type == "MARK_DUMMY_LOCOMOTIVE"\n    form_key = f"manual_override_form_{override_type}_{abs(hash(selected_label))}_{_clean(prefill.get(\'suggestion_id\'))}"\n',
        "manual ui dummy form flag",
    )
    text = replace_once(
        text,
        '        save_only = st.form_submit_button("Override speichern")\n        save_and_rebuild = st.form_submit_button("Speichern und neu prüfen", type="primary")\n',
        '        save_only = st.form_submit_button("Dummy-Lok speichern" if is_dummy_action else "Override speichern")\n        save_and_rebuild = st.form_submit_button("Dummy-Lok speichern und neu prüfen" if is_dummy_action else "Speichern und neu prüfen", type="primary")\n',
        "manual ui dummy button labels",
    )
    dummy_submit = r'''    if is_dummy_action:
        try:
            action = upsert_dummy_locomotive_mapping(
                loco_no=target_loco_no.strip(),
                reason=comment.strip(),
                changed_by=created_by.strip() or getpass.getuser(),
            )
        except ValueError as error:
            st.error(str(error))
            return
        st.success(f"Dummy-/Planungslok {target_loco_no.strip()} wurde gespeichert. Aktion: {action}.")
        if save_and_rebuild:
            with st.status("Dummy-Katalog wird gespeichert und sicher neu berechnet ...", expanded=True) as status:
                result = _run_pipeline(Path(run_all_script))
                if result.returncode == 0:
                    status.update(label="Neuberechnung erfolgreich abgeschlossen.", state="complete", expanded=False)
                    st.session_state["overview_refresh_completed"] = True
                    st.session_state["overview_refresh_completed_at"] = datetime.now().strftime("%d.%m.%Y um %H:%M")
                    st.rerun()
                status.update(label="Neuberechnung fehlgeschlagen.", state="error", expanded=True)
                st.error("Der letzte produktive DuckDB-Stand bleibt erhalten. Der Dummy-Katalogeintrag wurde gespeichert.")
                st.text_area("Fehler der Berechnung", result.stderr, height=220)
                st.text_area("Output der Berechnung", result.stdout, height=220)
        else:
            st.info("Bitte anschließend neu prüfen, damit Timeline, Quality Gate und Exporte aktualisiert werden.")
        return
'''
    text = replace_once(
        text,
        '    if override_type not in {"CLASSIFY_GAP", "CASE_NOTE"} and not override_value.strip():\n',
        dummy_submit + '    if override_type not in {"CLASSIFY_GAP", "CASE_NOTE"} and not override_value.strip():\n',
        "manual ui dummy submit branch",
    )
    text = replace_once(
        text,
        '    if CHANGE_LOG_PATH.exists():\n',
        '    if DUMMY_CHANGE_LOG_PATH.exists():\n        st.markdown("#### Als Dummy-/Planungslok markierte Fahrzeuge")\n        st.dataframe(\n            _read_csv_safe(DUMMY_CHANGE_LOG_PATH, DUMMY_CHANGE_LOG_COLUMNS),\n            use_container_width=True,\n            hide_index=True,\n        )\n    if CHANGE_LOG_PATH.exists():\n',
        "manual ui dummy audit display",
    )
    return text


def patch_csv(text: str) -> str:
    if "91806189000-3;" in text:
        return text
    if not text.endswith("\n"):
        text += "\n"
    return text + "91806189000-3;Zusaetzliche bekannte Planungs-/Dummy-Loknummer;Y\n"


def patch_historical_installer_test(text: str, phase: str) -> str:
    if HISTORICAL_TEST_MARKER in text:
        return text
    if phase == "6b":
        old = "PKG = Path(__file__).resolve().parents[1]\nspec = importlib.util.spec_from_file_location('installer', PKG / 'apply_rule_engine_hardening_phase6b.py')\ninstaller = importlib.util.module_from_spec(spec)\nassert spec.loader\nspec.loader.exec_module(installer)\n"
        new = "PKG = Path(__file__).resolve().parents[1]\n# NETZENTGELT_HISTORICAL_INSTALLER_TEST_SKIP_V1_20260609\nINSTALLER_PATH = PKG / 'apply_rule_engine_hardening_phase6b.py'\ninstaller = None\nif INSTALLER_PATH.exists():\n    spec = importlib.util.spec_from_file_location('installer', INSTALLER_PATH)\n    installer = importlib.util.module_from_spec(spec)\n    assert spec.loader\n    spec.loader.exec_module(installer)\n\ndef test_historical_phase6b_installer_artifact():\n    if installer is None:\n        import pytest\n        pytest.skip('Historischer Phase-6B-Installer wurde beim Repository-Cleanup entfernt.')\n"
        main_anchor = "def main() -> int:\n"
        main_insert = "def main() -> int:\n    if installer is None:\n        print('SKIP: historischer Phase-6B-Installer wurde beim Repository-Cleanup entfernt.')\n        return 0\n"
    else:
        old = 'ROOT = Path(__file__).resolve().parents[1]\nspec = importlib.util.spec_from_file_location("installer", ROOT / "apply_rule_engine_hardening_phase6c.py")\ninstaller = importlib.util.module_from_spec(spec)\nassert spec.loader is not None\nspec.loader.exec_module(installer)\n'
        new = 'ROOT = Path(__file__).resolve().parents[1]\n# NETZENTGELT_HISTORICAL_INSTALLER_TEST_SKIP_V1_20260609\nINSTALLER_PATH = ROOT / "apply_rule_engine_hardening_phase6c.py"\ninstaller = None\nif INSTALLER_PATH.exists():\n    spec = importlib.util.spec_from_file_location("installer", INSTALLER_PATH)\n    installer = importlib.util.module_from_spec(spec)\n    assert spec.loader is not None\n    spec.loader.exec_module(installer)\n\ndef test_historical_phase6c_installer_artifact():\n    if installer is None:\n        import pytest\n        pytest.skip("Historischer Phase-6C-Installer wurde beim Repository-Cleanup entfernt.")\n'
        main_anchor = "def main() -> int:\n"
        main_insert = 'def main() -> int:\n    if installer is None:\n        print("SKIP: historischer Phase-6C-Installer wurde beim Repository-Cleanup entfernt.")\n        return 0\n'
    text = replace_once(text, old, new, f"historical installer loader {phase}")
    return replace_once(text, main_anchor, main_insert, f"historical installer main guard {phase}")


PATCHERS = {
    "scripts/dummy_locomotive_module.py": patch_dummy_module,
    "scripts/manual_override_ui_module.py": patch_manual_ui,
    "data/01_mapping/dummy_locomotives.csv": patch_csv,
    "tests/test_installer_phase6b.py": lambda text: patch_historical_installer_test(text, "6b"),
    "tests/test_installer_phase6c.py": lambda text: patch_historical_installer_test(text, "6c"),
}


def latest_manifest() -> Path | None:
    if not BACKUP_ROOT.exists():
        return None
    manifests = sorted(BACKUP_ROOT.glob(f"*/{MANIFEST_NAME}"))
    return manifests[-1] if manifests else None


def validate_baseline(relative: str, raw: bytes, test_mode: bool) -> None:
    if test_mode:
        return
    expected = EXPECTED_BLOB_SHA[relative]
    if not accepted_sha(raw, expected):
        raise RuntimeError(
            f"Lokaler Stand von '{relative}' weicht vom geprüften GitHub-Stand ab. "
            f"Erwarteter Git-Blob: {expected}, lokal: {git_blob_sha(raw)}, "
            f"LF-normalisiert: {git_blob_sha(normalize_lf(raw))}. Bitte zuerst git status prüfen."
        )


def build_patched(root: Path, test_mode: bool) -> dict[str, bytes]:
    patched: dict[str, bytes] = {}
    for relative, patcher in PATCHERS.items():
        path = root / relative
        if not path.exists():
            raise RuntimeError(f"Erwartete Datei fehlt: {relative}")
        raw = path.read_bytes()
        text, has_bom, newline = decode_text(raw)
        if MARKER not in text and HISTORICAL_TEST_MARKER not in text:
            validate_baseline(relative, raw, test_mode)
        patched[relative] = encode_text(patcher(text), has_bom, newline)
    for relative, payload in NEW_FILES.items():
        source = ROOT / payload
        if not source.exists():
            raise RuntimeError(f"Payload fehlt: {payload}")
        patched[relative] = source.read_bytes()
    return patched


def verify_expected_state(root: Path) -> None:
    checks = {
        "scripts/dummy_locomotive_module.py": [MARKER, "upsert_dummy_locomotive_mapping", '"91806189000-3",'],
        "scripts/manual_override_ui_module.py": [MARKER, "MARK_DUMMY_LOCOMOTIVE", "upsert_dummy_locomotive_mapping"],
        "data/01_mapping/dummy_locomotives.csv": ["91806189000-3;"],
        "tests/test_installer_phase6b.py": [HISTORICAL_TEST_MARKER, "pytest.skip"],
        "tests/test_installer_phase6c.py": [HISTORICAL_TEST_MARKER, "pytest.skip"],
        "scripts/test_dummy_locomotive_ui_classification.py": ["NETZENTGELT_DUMMY_UI_CLASSIFICATION_TEST_V2_20260609"],
        "scripts/verify_dummy_locomotive_ui_classification.py": ["NETZENTGELT_DUMMY_UI_CLASSIFICATION_VERIFY_V2_20260609"],
    }
    for relative, markers in checks.items():
        path = root / relative
        if not path.exists():
            raise RuntimeError(f"Verifikationsdatei fehlt: {relative}")
        text = path.read_text(encoding="utf-8-sig")
        for marker in markers:
            if marker not in text:
                raise RuntimeError(f"Marker '{marker}' fehlt in {relative}")
    for relative in [
        "scripts/dummy_locomotive_module.py",
        "scripts/manual_override_ui_module.py",
        "tests/test_installer_phase6b.py",
        "tests/test_installer_phase6c.py",
        "scripts/test_dummy_locomotive_ui_classification.py",
        "scripts/verify_dummy_locomotive_ui_classification.py",
    ]:
        py_compile.compile(str(root / relative), doraise=True)


def dry_run(root: Path, test_mode: bool) -> int:
    build_patched(root, test_mode)
    print("OK: Dry Run erfolgreich. Keine Dateien wurden veraendert.")
    return 0


def _expected_state_present(root: Path) -> bool:
    try:
        verify_expected_state(root)
        return True
    except Exception:
        return False


def apply(root: Path, test_mode: bool) -> int:
    if _expected_state_present(root):
        print("OK: Hotfix ist bereits vollständig angewandt. Keine Dateien wurden erneut überschrieben.")
        return 0
    patched = build_patched(root, test_mode)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_%f")
    backup = BACKUP_ROOT / stamp
    backup.mkdir(parents=True, exist_ok=True)
    manifest = {"created_at_utc": stamp, "files": []}
    for relative, new_raw in patched.items():
        target = root / relative
        backup_target = backup / relative
        existed = target.exists()
        if existed:
            backup_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup_target)
        manifest["files"].append({"path": relative, "existed": existed})
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(new_raw)
    (backup / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    verify_expected_state(root)
    print(f"OK: Hotfix angewandt. Backup: {backup}")
    return 0


def verify(root: Path) -> int:
    verify_expected_state(root)
    print("OK: Marker, Katalogeintrag, historische Test-Skips und Python-Syntax verifiziert.")
    return 0


def rollback(root: Path) -> int:
    manifest_path = latest_manifest()
    if manifest_path is None:
        raise RuntimeError("Kein Backup-Manifest für Rollback gefunden.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    backup = manifest_path.parent
    for item in manifest["files"]:
        relative = item["path"]
        target = root / relative
        source = backup / relative
        if item["existed"]:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        elif target.exists():
            target.unlink()
    print(f"OK: Rollback abgeschlossen aus Backup: {backup}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["dry-run", "apply", "verify", "rollback"])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--test-mode", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "dry-run":
            return dry_run(args.root, args.test_mode)
        if args.command == "apply":
            return apply(args.root, args.test_mode)
        if args.command == "verify":
            return verify(args.root)
        return rollback(args.root)
    except Exception as error:
        print(f"FEHLER: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
