from __future__ import annotations

import tempfile
from pathlib import Path
import sys
import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import dummy_locomotive_module as mod


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        original_mapping = mod.DUMMY_MAPPING_PATH
        try:
            mod.DUMMY_MAPPING_PATH = root / "dummy_locomotives.csv"
            mod.DUMMY_MAPPING_PATH.write_text(
                "loco_no;reason;active_flag\n91850000002-4;Known planning loco;Y\n",
                encoding="utf-8",
            )
            con = duckdb.connect(":memory:")
            con.execute(
                """
                create table raw_locomotivemovement(
                    LocomotiveNo varchar,
                    LocomotiveType varchar,
                    TransportNumber varchar,
                    PerformingRU varchar,
                    OriginCountryISO varchar,
                    DestinationCountryISO varchar,
                    ActualDeparture varchar,
                    ActualArrival varchar
                )
                """
            )
            con.execute(
                """
                insert into raw_locomotivemovement values
                  ('REAL-1','Electric','T1','RU','DE','DE','2026-06-01 00:00:00','2026-06-01 01:00:00'),
                  ('91850000002-4','Planning Loco','T2','RU','DE','DE','2026-06-01 00:00:00','2026-06-01 01:00:00'),
                  ('AUTO-DUMMY','pLaNnInG DuMmY LoCo','T3','RU','DE','DE','2026-06-01 00:00:00','2026-06-01 01:00:00')
                """
            )
            con.execute(
                """
                create table stg_loco_events(
                    source_table varchar,
                    source_row_id bigint,
                    loco_no varchar,
                    transport_number varchar,
                    actual_departure_ts timestamp,
                    actual_arrival_ts timestamp
                )
                """
            )
            con.execute(
                """
                insert into stg_loco_events values
                  ('raw_locomotivemovement',1,'REAL-1','T1','2026-06-01 00:00:00','2026-06-01 01:00:00'),
                  ('raw_locomotivemovement',2,'91850000002-4','T2','2026-06-01 00:00:00','2026-06-01 01:00:00'),
                  ('raw_locomotivemovement',3,'AUTO-DUMMY','T3','2026-06-01 00:00:00','2026-06-01 01:00:00')
                """
            )
            con.execute(
                "create table stg_loco_events_skipped(source_table varchar, source_row_id bigint, skip_reason varchar)"
            )
            con.execute("create table dq_run_metadata(error_cutoff_utc timestamp)")
            con.execute("insert into dq_run_metadata values ('2026-06-02 00:00:00')")
            con.execute(
                """
                create table dq_findings(
                    run_id varchar,
                    severity varchar,
                    rule_id varchar,
                    rule_group varchar,
                    loco_no varchar,
                    transport_number varchar,
                    performing_ru varchar,
                    row_type varchar,
                    movement_sequence_no bigint,
                    period_start_utc timestamp,
                    period_end_utc timestamp,
                    message varchar,
                    suggested_action varchar,
                    status varchar,
                    source_table varchar,
                    source_row_id bigint,
                    overlap_with_transport_number varchar
                )
                """
            )
            con.execute(
                "insert into dq_findings values ('r','INFO','R003','TIME','91850000002-4','T2','RU','MOVEMENT',1,null,null,'bad','bad','info','x',1,null)"
            )

            mod.build_dummy_locomotive_catalog(con)
            assert con.execute(
                "select count(*) from cfg_dummy_locomotives_effective where loco_no='AUTO-DUMMY'"
            ).fetchone()[0] == 1
            mod.exclude_dummy_locomotives_from_staging(con)
            assert con.execute("select count(*) from stg_loco_events").fetchone()[0] == 1
            assert con.execute("select loco_no from stg_loco_events").fetchone()[0] == "REAL-1"
            mod.consolidate_dummy_locomotive_findings(con, "run")
            assert con.execute(
                "select count(*) from dq_findings where loco_no='91850000002-4' and rule_id<>'R012'"
            ).fetchone()[0] == 0
            assert con.execute(
                "select count(*) from dq_findings where rule_id='R012'"
            ).fetchone()[0] == 2
        finally:
            mod.DUMMY_MAPPING_PATH = original_mapping

    print(
        "OK: Dummy-Katalog, case-insensitive LocomotiveType-Erkennung, "
        "Ausschluss und R012-Konsolidierung erfolgreich."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
