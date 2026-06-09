from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
import duckdb

ROOT = Path(__file__).resolve().parent
INSTALLER_PATH = ROOT / "apply_dummy_locomotive_verify_schema_hotfix.py"
PAYLOAD = ROOT / "payload" / "scripts" / "verify_dummy_locomotive_hardening.py"
OLD = ROOT / "fixtures" / "verify_dummy_locomotive_hardening_old.py"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def create_fixture_db(path: Path, include_dummy_export: bool = False) -> None:
    con = duckdb.connect(str(path))
    known = [
        "91850000002-4","00000000011-7","00000000000-0","00000000003-4","00000000013-3",
        "00000000010-9","00000000008-3","00000000015-8","00000000004-2","00000000009-1",
        "00000000005-9","00000000006-7","00000000007-5","91850000007-3","91850000008-1",
        "91850000003-2","91850000004-0","91850000001-6","00000000002-6","00000000014-1","00000000001-8",
    ]
    con.execute("create table cfg_dummy_locomotives_effective(loco_no varchar)")
    con.executemany("insert into cfg_dummy_locomotives_effective values (?)", [(v,) for v in known])
    con.execute("create table audit_excluded_dummy_locomotives(loco_no varchar)")
    con.execute("create table audit_excluded_dummy_locomotive_staging(loco_no varchar)")
    con.execute("insert into audit_excluded_dummy_locomotive_staging values ('91850000002-4')")
    con.execute("create table stg_loco_events(loco_no varchar)")
    con.execute("insert into stg_loco_events values ('REAL-1')")
    con.execute("create table core_loco_timeline(loco_no varchar)")
    con.execute("insert into core_loco_timeline values ('REAL-1')")
    con.execute("create table dq_findings(loco_no varchar, rule_id varchar, row_type varchar)")
    con.execute("insert into dq_findings values ('91850000002-4','R012','RAW_DUMMY_LOCOMOTIVE')")
    con.execute('create table export_zuordnungen("TfzE oder tEns*" varchar, "Beginn der Zuordnung*" timestamp)')
    con.execute('create table export_nutzungsmeldung("TfzE oder tEns*" varchar, "Beginn der Nutzung*" timestamp)')
    con.execute("create table raw_locomotivemovement(LocomotiveNo varchar, LocomotiveType varchar)")
    con.execute("insert into raw_locomotivemovement values ('REAL-1','Electric'),('91850000002-4','Planning Dummy')")
    if include_dummy_export:
        con.execute('insert into export_zuordnungen values (\'91850000002-4\', current_timestamp)')
    else:
        con.execute('insert into export_zuordnungen values (\'REAL-1\', current_timestamp)')
    con.execute('insert into export_nutzungsmeldung values (\'REAL-1\', current_timestamp)')
    con.close()


def main() -> int:
    installer = load(INSTALLER_PATH, "verify_schema_installer")
    with tempfile.TemporaryDirectory() as tmp_text:
        project = Path(tmp_text)
        (project / "scripts").mkdir(parents=True)
        shutil.copy2(OLD, project / "scripts" / "verify_dummy_locomotive_hardening.py")
        original = (project / "scripts" / "verify_dummy_locomotive_hardening.py").read_bytes()
        installer.EXPECTED_OLD_GIT_BLOB = installer.git_blob_sha(installer.lf_bytes(original))
        assert installer.dry_run(project) == 0
        assert (project / "scripts" / "verify_dummy_locomotive_hardening.py").read_bytes() == original
        assert installer.apply(project) == 0
        assert installer.verify(project) == 0
        assert installer.apply(project) == 0
        assert b"\r\n" in (project / "scripts" / "verify_dummy_locomotive_hardening.py").read_bytes()
        assert installer.rollback(project) == 0
        assert (project / "scripts" / "verify_dummy_locomotive_hardening.py").read_bytes() == original

    verifier = load(PAYLOAD, "verify_schema_payload")
    with tempfile.TemporaryDirectory() as tmp_text:
        root = Path(tmp_text)
        good_db = root / "good.duckdb"
        bad_db = root / "bad.duckdb"
        create_fixture_db(good_db, include_dummy_export=False)
        create_fixture_db(bad_db, include_dummy_export=True)
        assert verifier.verify(good_db) == 0
        assert verifier.verify(bad_db) == 1

    print("OK: Installer, CRLF, Idempotenz, Rollback und produktionsnahes Export-Schema erfolgreich getestet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
