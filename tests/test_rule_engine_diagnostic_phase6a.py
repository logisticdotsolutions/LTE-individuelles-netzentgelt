from __future__ import annotations

import csv
import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
INSTALLER = PACKAGE_ROOT / "apply_rule_engine_diagnostic_phase6a.py"
PAYLOAD = PACKAGE_ROOT / "payload" / "scripts" / "rule_engine_diagnostic_phase6a.py"


def run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(INSTALLER), *args],
        cwd=str(cwd or PACKAGE_ROOT),
        text=True,
        capture_output=True,
    )


def test_installer_roundtrip() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "scripts").mkdir(parents=True)
        (root / "app").mkdir(parents=True)
        (root / "payload" / "scripts").mkdir(parents=True)
        (root / "scripts" / "run_all.py").write_bytes(b"print('run')\r\n")
        (root / "app" / "app.py").write_bytes(b"print('app')\r\n")
        (root / "payload" / "scripts" / PAYLOAD.name).write_bytes(PAYLOAD.read_bytes())
        (root / "apply_rule_engine_diagnostic_phase6a.py").write_bytes(INSTALLER.read_bytes())

        result = run("dry-run", "--project-root", str(root), cwd=root)
        assert result.returncode == 0, result.stdout + result.stderr
        assert not (root / "scripts" / PAYLOAD.name).exists()

        result = run("apply", "--project-root", str(root), cwd=root)
        assert result.returncode == 0, result.stdout + result.stderr
        installed = root / "scripts" / PAYLOAD.name
        assert installed.exists()
        raw = installed.read_bytes()
        assert b"\r\n" in raw, "Windows-CRLF was not preserved for new file"

        result = run("verify", "--project-root", str(root), cwd=root)
        assert result.returncode == 0, result.stdout + result.stderr

        result = run("apply", "--project-root", str(root), cwd=root)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "bereits vollständig installiert" in result.stdout

        result = run("rollback", "--project-root", str(root), cwd=root)
        assert result.returncode == 0, result.stdout + result.stderr
        assert not installed.exists(), "Rollback must remove newly created script"


def import_payload_module():
    spec = importlib.util.spec_from_file_location("rule_engine_diagnostic_phase6a", PAYLOAD)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_payload_structure() -> None:
    module = import_payload_module()
    source = PAYLOAD.read_text(encoding="utf-8")
    assert module.PHASE_ID == "NETZENTGELT_RULE_ENGINE_DIAGNOSTIC_PHASE6A_V1_20260608"
    assert "read_only=True" in source
    for check_id in [f"D{i:03d}" for i in range(1, 22)]:
        assert check_id in source, f"Missing diagnostic check {check_id}"


def test_optional_duckdb_fixture() -> None:
    try:
        import duckdb  # type: ignore
    except ImportError:
        print("SKIP: duckdb package not installed in this Python environment")
        return

    module = import_payload_module()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "netzentgelt.duckdb"
        raw_dir = root / "raw"
        out_dir = root / "report"
        raw_dir.mkdir()
        with (raw_dir / "LocomotiveMovement.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter=";")
            writer.writerow(["TransportNumber", "LocomotiveNo"])
            writer.writerow(["T1", "L1"])
        con = duckdb.connect(str(db_path))
        try:
            con.execute("""
                create table cfg_loco_mapping (
                    loco_no varchar, tfze_or_tens varchar, halter_name varchar,
                    default_vens varchar, valid_from_utc varchar, valid_to_utc varchar,
                    priority varchar, source varchar, active_flag varchar
                )
            """)
            con.execute("insert into cfg_loco_mapping values ('L1','L1','Holder A','V1',null,null,'1','A','Y')")
            con.execute("insert into cfg_loco_mapping values ('L1','L1','Holder B','V2',null,null,'2','B','Y')")
            con.execute("""
                create table cfg_market_partner_mapping_effective (
                    role_code varchar, source_value_normalized varchar, market_partner_id varchar
                )
            """)
            con.execute("""
                create table cfg_market_partner_role_effective (
                    role_code varchar, company_name_normalized varchar, market_partner_id varchar
                )
            """)
            con.execute("insert into cfg_market_partner_mapping_effective values ('ANE_TENS','holdera','ANE-1')")
            con.execute("""
                create table core_loco_timeline (
                    row_type varchar, report_scope varchar, loco_no varchar, transport_number varchar,
                    performing_ru varchar, holder_name varchar, holder_market_partner_id varchar,
                    user_vens varchar, performing_ru_marktpartner_id varchar,
                    period_start_utc timestamp, period_end_utc timestamp,
                    actual_departure_ts timestamp, actual_arrival_ts timestamp,
                    sequence_ts timestamp, sort_sequence double,
                    origin_name varchar, destination_name varchar,
                    de_event_label varchar, gap_relevant_de boolean,
                    gap_duration_minutes bigint, export_ready boolean,
                    dq_severity varchar, dq_message varchar,
                    source_table varchar, source_row_id bigint
                )
            """)
            con.execute("""
                insert into core_loco_timeline values
                ('MOVEMENT','IN_REPORT','L1','T1','RU','Holder A','WRONG',null,null,
                 '2026-06-06 00:00:00','2026-06-06 02:00:00','2026-06-06 00:00:00','2026-06-06 02:00:00',
                 '2026-06-06 00:00:00',1,'A','B','In DE',false,null,false,'','', 'raw_locomotivemovement',1),
                ('MOVEMENT','IN_REPORT','L1','T2','RU','Holder A','WRONG',null,null,
                 '2026-06-06 01:00:00','2026-06-06 03:00:00','2026-06-06 01:00:00','2026-06-06 03:00:00',
                 '2026-06-06 01:00:00',2,'B','C','In DE',false,null,false,'','', 'raw_locomotivemovement',2)
            """)
            con.execute("create table dq_findings (rule_id varchar, severity varchar, row_type varchar, loco_no varchar, transport_number varchar, period_start_utc timestamp, period_end_utc timestamp, message varchar, source_table varchar, source_row_id bigint)")
            con.execute("create table dq_export_gate (loco_no varchar, coverage_date date, gate_status varchar, error_findings bigint, manual_review_findings bigint, overlap_minutes bigint, long_gap_rows bigint)")
            con.execute("insert into dq_export_gate values ('L1','2026-06-06','BLOCKED',0,0,0,0)")
            con.execute("create table dq_run_metadata (error_cutoff_utc timestamp)")
            con.execute("insert into dq_run_metadata values ('2026-06-07 00:00:00')")
            con.execute("create table dq_global_export_blockers (blocker_date date, rule_id varchar, severity varchar, row_type varchar, transport_number varchar, performing_ru varchar, message varchar)")
            con.execute("create table raw_import_run (source_file varchar, target_table varchar, row_count bigint, imported_at_utc varchar, status varchar)")
            con.execute("insert into raw_import_run values ('LocomotiveMovement.csv','raw_locomotivemovement',1,'2026-06-08T00:00:00Z','imported')")
            con.execute("create table raw_transportdetail (TransportNumber varchar, FirstLocomotiveNo varchar, OriginCountryISO varchar, DestinationCountryISO varchar)")
        finally:
            con.close()

        module.run_diagnostics(db_path=db_path, raw_dir=raw_dir, output_dir=out_dir)
        summary = (out_dir / "summary.csv").read_text(encoding="utf-8-sig")
        assert "D001" in summary and "D005" in summary and "D006" in summary
        assert (out_dir / "README_DIAGNOSTIC_REPORT.md").exists()


def main() -> int:
    test_installer_roundtrip()
    print("OK: installer dry-run/apply/verify/idempotency/rollback")
    test_payload_structure()
    print("OK: payload structure and read-only markers")
    test_optional_duckdb_fixture()
    print("OK: optional DuckDB fixture (or explicitly skipped without duckdb)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
