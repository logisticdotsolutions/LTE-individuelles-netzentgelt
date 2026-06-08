from __future__ import annotations

import csv
from pathlib import Path

import pytest

import manual_override_module
import run_all
from tests.support.builders import create_empty_raw_sources


def write_override_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=manual_override_module.OVERRIDE_COLUMNS, delimiter=";")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in manual_override_module.OVERRIDE_COLUMNS})


@pytest.mark.integration
def test_cancelled_transport_is_excluded_centrally_and_audited(con):
    create_empty_raw_sources(con)
    con.execute("insert into raw_transportdetail values ('TR-CANCEL', 'Cancelled', '1', 'DE', 'DE', '2026-06-01T10:00:00', '2026-06-01T11:00:00', '9180', 'Train movement')")
    con.execute("insert into raw_transportdetail values ('TR-VALID', 'Planned', '1', 'DE', 'DE', '2026-06-01T12:00:00', '2026-06-01T13:00:00', '9181', 'Train movement')")
    con.execute("insert into raw_locomotivemovement values ('9180', null, 'RU', '2026-06-01T10:00:00', '2026-06-01T11:00:00', 'DE', 'DE', 'TR-CANCEL', 'Holder', 'A', 'B')")
    con.execute("insert into raw_locomotivemovement values ('9181', null, 'RU', '2026-06-01T12:00:00', '2026-06-01T13:00:00', 'DE', 'DE', 'TR-VALID', 'Holder', 'A', 'B')")
    run_all.build_cancelled_transport_exclusions(con)
    run_all.build_loco_events(con)
    assert con.execute("select transport_number from cfg_excluded_cancelled_transports").fetchall() == [("TR-CANCEL",)]
    assert con.execute("select transport_number from stg_loco_events").fetchall() == [("TR-VALID",)]
    assert con.execute("select count(*) from audit_excluded_cancelled_transports where transport_number='TR-CANCEL'").fetchone()[0] == 2


@pytest.mark.integration
def test_manual_override_updates_temp_raw_tables_and_writes_audit_without_touching_csv(con, tmp_path: Path, monkeypatch):
    override_path = tmp_path / "manual_overrides.csv"
    write_override_csv(
        override_path,
        [{
            "override_id": "OV-1", "active_flag": "Y", "override_type": "SET_LOCO_NO",
            "transport_number": "TR-OVERRIDE", "override_value": "91800009999-9",
            "comment": "fixture", "created_by": "pytest", "created_at_utc": "2026-06-08T10:00:00Z",
        }],
    )
    original_bytes = override_path.read_bytes()
    monkeypatch.setattr(manual_override_module, "MANUAL_OVERRIDE_PATH", override_path)
    monkeypatch.setattr(manual_override_module, "MAP_DIR", tmp_path)
    create_empty_raw_sources(con)
    con.execute("insert into raw_locomotivemovement values (null, null, 'RU', '2026-06-01T10:00:00', '2026-06-01T11:00:00', 'DE', 'DE', 'TR-OVERRIDE', 'Holder', 'A', 'B')")
    con.execute("insert into raw_transportdetail values ('TR-OVERRIDE', 'Planned', '1', 'DE', 'DE', '2026-06-01T10:00:00', '2026-06-01T11:00:00', null, 'Train movement')")
    manual_override_module.import_manual_overrides(con)
    manual_override_module.apply_raw_manual_overrides(con, "RUN_TEST")
    assert con.execute("select LocomotiveNo from raw_locomotivemovement").fetchone()[0] == "91800009999-9"
    assert con.execute("select FirstLocomotiveNo from raw_transportdetail").fetchone()[0] == "91800009999-9"
    assert con.execute("select sum(affected_rows) from audit_manual_override_application where application_status='APPLIED'").fetchone()[0] == 2
    assert override_path.read_bytes() == original_bytes


@pytest.mark.integration
def test_conflicting_active_manual_overrides_abort_early(con, tmp_path: Path, monkeypatch):
    override_path = tmp_path / "manual_overrides.csv"
    write_override_csv(
        override_path,
        [
            {"override_id": "OV-A", "active_flag": "Y", "override_type": "SET_LOCO_NO", "transport_number": "TR-X", "override_value": "9180"},
            {"override_id": "OV-B", "active_flag": "Y", "override_type": "SET_LOCO_NO", "transport_number": "TR-X", "override_value": "9181"},
        ],
    )
    monkeypatch.setattr(manual_override_module, "MANUAL_OVERRIDE_PATH", override_path)
    monkeypatch.setattr(manual_override_module, "MAP_DIR", tmp_path)
    with pytest.raises(manual_override_module.ManualOverrideError, match="Widersprüchliche aktive manuelle Overrides"):
        manual_override_module.import_manual_overrides(con)
