from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime

CORE_COLUMNS = {
    "run_id": "varchar", "row_type": "varchar", "loco_no": "varchar", "tfze_or_tens": "varchar",
    "sort_sequence": "double", "movement_sequence_no": "bigint", "period_start_utc": "timestamp",
    "period_end_utc": "timestamp", "sequence_ts": "timestamp", "sequence_ts_source": "varchar",
    "sequence_ts_reason": "varchar", "actual_departure_ts": "timestamp", "actual_arrival_ts": "timestamp",
    "holder_name": "varchar", "performing_ru": "varchar", "cal_start_country": "varchar",
    "cal_end_country": "varchar", "cal_entry_count_home": "bigint", "cal_exit_count_home": "bigint",
    "cal_route_type_home": "varchar", "performing_ru_marktpartner_id": "varchar",
    "performing_ru_marktpartner_id_source": "varchar", "holder_market_partner_id": "varchar",
    "holder_market_partner_id_source": "varchar", "user_vens": "varchar", "exempt_vens": "boolean",
    "exempt_tens": "boolean", "vens_tens_exception_flag": "boolean", "vens_tens_exception_comment": "varchar",
    "country": "varchar", "origin_country_iso": "varchar", "destination_country_iso": "varchar",
    "clean_dir": "varchar", "faulty_dir": "varchar", "report_scope": "varchar", "de_event_label": "varchar",
    "traction_type": "varchar", "transport_number": "varchar", "train_no": "varchar", "distance": "varchar",
    "origin_name": "varchar", "destination_name": "varchar", "next_origin_name": "varchar",
    "next_origin_country_iso": "varchar", "gap_from_utc": "timestamp", "gap_to_utc": "timestamp",
    "gap_duration_minutes": "bigint", "gap_duration_text": "varchar", "gap_message": "varchar",
    "gap_relevant_de": "boolean", "confidence": "varchar", "decision_reason": "varchar",
    "needs_manual_review": "boolean", "export_ready": "boolean", "dq_severity": "varchar",
    "dq_message": "varchar", "assignment_reason": "varchar", "source_table": "varchar",
    "source_row_id": "bigint", "display_sequence_no": "bigint",
}

FINDING_COLUMNS = {
    "run_id": "varchar", "severity": "varchar", "rule_id": "varchar", "rule_group": "varchar",
    "loco_no": "varchar", "transport_number": "varchar", "performing_ru": "varchar", "row_type": "varchar",
    "movement_sequence_no": "bigint", "period_start_utc": "timestamp", "period_end_utc": "timestamp",
    "message": "varchar", "suggested_action": "varchar", "status": "varchar", "source_table": "varchar",
    "source_row_id": "bigint", "overlap_with_transport_number": "varchar",
}


def qident(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def create_table(con, name: str, columns: Mapping[str, str]) -> None:
    ddl = ", ".join(f"{qident(column)} {data_type}" for column, data_type in columns.items())
    con.execute(f"create or replace table {qident(name)} ({ddl})")


def insert_row(con, table: str, row: Mapping[str, object]) -> None:
    columns = list(row)
    placeholders = ", ".join("?" for _ in columns)
    names = ", ".join(qident(column) for column in columns)
    con.execute(f"insert into {qident(table)} ({names}) values ({placeholders})", [row[column] for column in columns])


def create_core_timeline(con) -> None:
    create_table(con, "core_loco_timeline", CORE_COLUMNS)


def movement(row_id: int = 1, **overrides: object) -> dict[str, object]:
    start = datetime(2026, 6, 1, 10, 0)
    end = datetime(2026, 6, 1, 11, 0)
    row: dict[str, object] = {
        "run_id": "RUN_TEST", "row_type": "MOVEMENT", "loco_no": "91800000001-1", "tfze_or_tens": "91800000001-1",
        "sort_sequence": float(row_id), "movement_sequence_no": row_id, "period_start_utc": start, "period_end_utc": end,
        "sequence_ts": start, "sequence_ts_source": "ActualDeparture", "sequence_ts_reason": "fixture",
        "actual_departure_ts": start, "actual_arrival_ts": end, "holder_name": "Holder GmbH", "performing_ru": "RU GmbH",
        "cal_start_country": "DE", "cal_end_country": "DE", "cal_entry_count_home": 0, "cal_exit_count_home": 0,
        "cal_route_type_home": "Inland", "performing_ru_marktpartner_id": None, "performing_ru_marktpartner_id_source": "UNRESOLVED",
        "holder_market_partner_id": None, "holder_market_partner_id_source": "UNRESOLVED", "user_vens": "RU GmbH",
        "exempt_vens": False, "exempt_tens": False, "vens_tens_exception_flag": False, "vens_tens_exception_comment": None,
        "country": "DE", "origin_country_iso": "DE", "destination_country_iso": "DE", "clean_dir": "IN", "faulty_dir": None,
        "report_scope": "IN_REPORT", "de_event_label": "In DE", "traction_type": "electric", "transport_number": f"TR-{row_id}",
        "train_no": f"TN-{row_id}", "distance": "10", "origin_name": f"Ort-{row_id}", "destination_name": f"Ort-{row_id + 1}",
        "next_origin_name": None, "next_origin_country_iso": None, "gap_from_utc": None, "gap_to_utc": None,
        "gap_duration_minutes": None, "gap_duration_text": None, "gap_message": None, "gap_relevant_de": False,
        "confidence": "MEDIUM", "decision_reason": "fixture", "needs_manual_review": False, "export_ready": True,
        "dq_severity": "", "dq_message": "", "assignment_reason": "fixture", "source_table": "raw_locomotivemovement",
        "source_row_id": row_id, "display_sequence_no": row_id,
    }
    row.update(overrides)
    return row


def gap(row_id: int = 1, minutes: int = 60, **overrides: object) -> dict[str, object]:
    start = datetime(2026, 6, 1, 11, 0)
    end = datetime(2026, 6, 1, 12, 0)
    row = movement(row_id)
    row.update({
        "row_type": "GAP", "sort_sequence": row_id + 0.5, "period_start_utc": start, "period_end_utc": end,
        "sequence_ts": None, "sequence_ts_source": "GAP", "actual_departure_ts": None, "actual_arrival_ts": None,
        "performing_ru": None, "gap_from_utc": start, "gap_to_utc": end, "gap_duration_minutes": minutes,
        "gap_duration_text": f"{minutes} Minuten", "gap_message": f"Fixture GAP {minutes}", "gap_relevant_de": True,
        "needs_manual_review": minutes > 480, "export_ready": False, "dq_severity": "ERROR" if minutes > 480 else "INFO",
        "source_row_id": row_id,
    })
    row.update(overrides)
    return row


def create_raw_import_run(con, snapshot: str = "2026-06-08T12:00:00Z") -> None:
    con.execute("""
        create or replace table raw_import_run (
            run_id varchar, imported_at_utc varchar, source_snapshot_at_utc varchar,
            source_file varchar, target_table varchar, source_hash varchar,
            row_count bigint, status varchar, error_message varchar
        )
    """)
    con.execute("insert into raw_import_run values ('RUN_TEST', ?, ?, 'fixture.csv', 'fixture', 'hash', 1, 'imported', null)", [snapshot, snapshot])


def create_empty_raw_sources(con) -> None:
    con.execute("create or replace table cfg_excluded_cancelled_transports (transport_number varchar, transport_status varchar)")
    con.execute("""
        create or replace table raw_locomotivemovement (
            LocomotiveNo varchar, LocomotiveType varchar, CurrentContractant varchar,
            ActualDeparture varchar, ActualArrival varchar, OriginCountryISO varchar,
            DestinationCountryISO varchar, TransportNumber varchar, LocomotiveHolder varchar,
            LocomotiveOriginLocationName varchar, LocomotiveDestinationLocationName varchar
        )
    """)
    con.execute("""
        create or replace table raw_transportdetail (
            TransportNumber varchar, TransportStatus varchar, SequenceID varchar,
            OriginCountryISO varchar, DestinationCountryISO varchar, ActualDeparture varchar,
            ActualArrival varchar, FirstLocomotiveNo varchar, MovementType varchar
        )
    """)


def prepare_base(con, rows: Iterable[Mapping[str, object]] = (), snapshot: str = "2026-06-08T12:00:00Z") -> None:
    create_raw_import_run(con, snapshot=snapshot)
    create_empty_raw_sources(con)
    create_core_timeline(con)
    for row in rows:
        insert_row(con, "core_loco_timeline", row)


def build_base_findings(con, rows: Iterable[Mapping[str, object]] = (), snapshot: str = "2026-06-08T12:00:00Z") -> None:
    import error_rules
    prepare_base(con, rows=rows, snapshot=snapshot)
    error_rules.build_findings(con, "RUN_TEST")


def create_findings_shell(con) -> None:
    create_table(con, "dq_findings", FINDING_COLUMNS)


def create_rule_catalog_shell(con) -> None:
    con.execute("""
        create or replace table cfg_dq_rule_catalog (
            rule_id varchar, rule_group varchar, severity_policy varchar,
            description varchar, active_flag boolean
        )
    """)


def ensure_phase6c_columns(con) -> None:
    existing = {row[0].lower() for row in con.execute("describe core_loco_timeline").fetchall()}
    for name, data_type in {
        "gap_time_basis_safe": "boolean", "gap_context_class": "varchar",
        "de_period_start_utc": "timestamp", "de_period_end_utc": "timestamp",
        "export_blocking": "boolean",
    }.items():
        if name.lower() not in existing:
            con.execute(f"alter table core_loco_timeline add column {qident(name)} {data_type}")


def create_dq_metadata(con, cutoff: str = "2026-06-07T12:00:00Z") -> None:
    con.execute("""
        create or replace table dq_run_metadata as
        select 'RUN_TEST'::varchar as run_id,
               '2026-06-08T12:00:00Z'::timestamp as source_snapshot_at_utc,
               ?::timestamp as error_cutoff_utc,
               current_timestamp as calculated_at_utc
    """, [cutoff])
