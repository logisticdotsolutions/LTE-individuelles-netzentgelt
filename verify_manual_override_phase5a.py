#!/usr/bin/env python3
"""Fachlicher Smoke-Test für Netzentgelt MVP Phase 5A."""
from __future__ import annotations

import csv
import importlib.util
import shutil
import sys
import tempfile
from pathlib import Path

import duckdb

PKG = Path(__file__).resolve().parent
PAYLOAD = PKG / "payload" / "manual_override_module.py"


def write_csv(path: Path, columns: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("manual_override_module", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        scripts = root / "scripts"
        scripts.mkdir(parents=True)
        module_path = scripts / "manual_override_module.py"
        shutil.copy2(PAYLOAD, module_path)
        module = load_module(module_path)

        rows = [
            {
                "override_id": "OVR_LOCO",
                "active_flag": "Y",
                "override_type": "SET_LOCO_NO",
                "transport_number": "T1",
                "target_loco_no": "",
                "target_actual_departure_utc": "",
                "target_actual_arrival_utc": "",
                "target_source_table": "",
                "target_source_row_id": "",
                "override_value": "91806189042-7",
                "classification_code": "",
                "comment": "Loknummer aus angrenzender Bewegung bestätigt",
                "created_by": "tester",
                "created_at_utc": "2026-06-07T10:00:00Z",
                "updated_at_utc": "2026-06-07T10:00:00Z",
            },
            {
                "override_id": "OVR_RU",
                "active_flag": "Y",
                "override_type": "SET_PERFORMING_RU",
                "transport_number": "T2",
                "target_loco_no": "L2",
                "target_actual_departure_utc": "2026-06-06T10:00:00",
                "target_actual_arrival_utc": "",
                "target_source_table": "",
                "target_source_row_id": "",
                "override_value": "LTE NL - LTE Netherlands B.V.",
                "classification_code": "",
                "comment": "PerformingRU bestätigt",
                "created_by": "tester",
                "created_at_utc": "2026-06-07T10:01:00Z",
                "updated_at_utc": "2026-06-07T10:01:00Z",
            },
            {
                "override_id": "OVR_DEP",
                "active_flag": "Y",
                "override_type": "SET_ACTUAL_DEPARTURE",
                "transport_number": "T3",
                "target_loco_no": "L3",
                "target_actual_departure_utc": "2026-06-06T11:00:00",
                "target_actual_arrival_utc": "",
                "target_source_table": "",
                "target_source_row_id": "",
                "override_value": "2026-06-06T11:15:00",
                "classification_code": "",
                "comment": "Grenzstationszeit fachlich korrigiert",
                "created_by": "tester",
                "created_at_utc": "2026-06-07T10:02:00Z",
                "updated_at_utc": "2026-06-07T10:02:00Z",
            },
            {
                "override_id": "OVR_SEQ",
                "active_flag": "Y",
                "override_type": "SET_SEQUENCE_TS",
                "transport_number": "T4",
                "target_loco_no": "L4",
                "target_actual_departure_utc": "2026-06-06T12:00:00",
                "target_actual_arrival_utc": "",
                "target_source_table": "",
                "target_source_row_id": "4",
                "override_value": "2026-06-06T12:15:00",
                "classification_code": "",
                "comment": "GPS-Grenzpunkt bestätigt",
                "created_by": "tester",
                "created_at_utc": "2026-06-07T10:03:00Z",
                "updated_at_utc": "2026-06-07T10:03:00Z",
            },
            {
                "override_id": "OVR_GAP",
                "active_flag": "Y",
                "override_type": "CLASSIFY_GAP",
                "transport_number": "",
                "target_loco_no": "L5",
                "target_actual_departure_utc": "2026-06-06T13:00:00",
                "target_actual_arrival_utc": "2026-06-06T20:00:00",
                "target_source_table": "core_loco_timeline",
                "target_source_row_id": "5",
                "override_value": "",
                "classification_code": "COLD_STAND",
                "comment": "Mögliche kalte Abstellung dokumentiert",
                "created_by": "tester",
                "created_at_utc": "2026-06-07T10:04:00Z",
                "updated_at_utc": "2026-06-07T10:04:00Z",
            },
        ]
        write_csv(root / "data" / "01_mapping" / "manual_overrides.csv", module.OVERRIDE_COLUMNS, rows)

        con = duckdb.connect(":memory:")
        con.execute("""
            create table raw_locomotivemovement (
                TransportNumber varchar,
                LocomotiveNo varchar,
                CurrentContractant varchar,
                ActualDeparture varchar,
                ActualArrival varchar
            )
        """)
        con.execute("""
            insert into raw_locomotivemovement values
                ('T1', null, 'LTE DE - LTE Germany GmbH', '2026-06-06T09:00:00', '2026-06-06T09:30:00'),
                ('T2', 'L2', null, '2026-06-06T10:00:00', '2026-06-06T10:30:00'),
                ('T3', 'L3', 'LTE DE - LTE Germany GmbH', '2026-06-06T11:00:00', '2026-06-06T11:30:00'),
                ('T4', 'L4', 'LTE DE - LTE Germany GmbH', '2026-06-06T12:00:00', '2026-06-06T12:30:00')
        """)
        con.execute("""
            create table raw_transportdetail (
                TransportNumber varchar,
                FirstLocomotiveNo varchar,
                ActualDeparture varchar
            )
        """)
        con.execute("""
            insert into raw_transportdetail values
                ('T1', null, '2026-06-06T09:00:00'),
                ('T2', 'L2', '2026-06-06T10:00:00')
        """)

        module.import_manual_overrides(con)
        module.apply_raw_manual_overrides(con, "RUN_TEST")

        assert con.execute("select LocomotiveNo from raw_locomotivemovement where TransportNumber='T1'").fetchone()[0] == "91806189042-7"
        assert con.execute("select FirstLocomotiveNo from raw_transportdetail where TransportNumber='T1'").fetchone()[0] == "91806189042-7"
        assert con.execute("select CurrentContractant from raw_locomotivemovement where TransportNumber='T2'").fetchone()[0] == "LTE NL - LTE Netherlands B.V."
        assert str(con.execute("select ActualDeparture from raw_locomotivemovement where TransportNumber='T3'").fetchone()[0]) == "2026-06-06T11:15:00"

        con.execute("""
            create table stg_loco_events (
                loco_no varchar,
                transport_number varchar,
                actual_departure_ts timestamp,
                sequence_ts timestamp,
                sequence_ts_source varchar,
                sequence_ts_reason varchar,
                source_row_id bigint
            )
        """)
        con.execute("""
            insert into stg_loco_events values
                ('L4', 'T4', timestamp '2026-06-06 12:00:00', timestamp '2026-06-06 12:00:00', 'ActualDeparture', 'Alt', 4)
        """)
        module.apply_staging_manual_overrides(con, "RUN_TEST")
        sequence = con.execute("select sequence_ts, sequence_ts_source from stg_loco_events where transport_number='T4'").fetchone()
        assert str(sequence[0]) == "2026-06-06 12:15:00"
        assert sequence[1] == "MANUAL_OVERRIDE"

        statuses = con.execute("select override_id, application_status from audit_manual_override_application order by override_id, phase").fetchall()
        assert ("OVR_GAP", "DOCUMENTED_ONLY") in statuses
        assert ("OVR_SEQ", "APPLIED") in statuses
        assert con.execute("select count(*) from dq_manual_override_conflicts").fetchone()[0] == 0

        # Konfliktprüfung: aktive widersprüchliche Werte für dasselbe Ziel müssen stoppen.
        rows.append({**rows[1], "override_id": "OVR_RU_CONFLICT", "override_value": "LTE DE - LTE Germany GmbH"})
        write_csv(root / "data" / "01_mapping" / "manual_overrides.csv", module.OVERRIDE_COLUMNS, rows)
        failed = False
        try:
            module.import_manual_overrides(con)
        except module.ManualOverrideError:
            failed = True
        assert failed, "Konfliktprüfung hat widersprüchliche aktive Overrides nicht gestoppt"
        con.close()

    print("MANUAL OVERRIDE PHASE5A SMOKE TEST OK")


if __name__ == "__main__":
    main()
