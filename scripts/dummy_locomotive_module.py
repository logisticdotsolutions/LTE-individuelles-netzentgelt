"""
Zentraler, auditierbarer Ausschluss von Planungs- und Dummy-Lokomotiven.

Bekannte Dummy-Loknummern werden in data/01_mapping/dummy_locomotives.csv gepflegt.
Zusätzlich werden alle LocomotiveMovement-Zeilen erkannt, deren LocomotiveType
unabhängig von Gross-/Kleinschreibung die Zeichenfolge "dummy" enthält.

Dummy-Loks bleiben über Audit-Tabellen und verdichtete R012-Findings sichtbar,
werden aber nicht wie reale Fahrzeuge in Timeline, GAP, Quality Gate oder Export
verarbeitet.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
DUMMY_MAPPING_PATH = ROOT / "data" / "01_mapping" / "dummy_locomotives.csv"
MARKER = "NETZENTGELT_DUMMY_LOCOMOTIVE_HARDENING_V1_20260608"

DEFAULT_DUMMY_LOCOMOTIVES = (
    "91850000002-4",
    "00000000011-7",
    "00000000000-0",
    "00000000003-4",
    "00000000013-3",
    "00000000010-9",
    "00000000008-3",
    "00000000015-8",
    "00000000004-2",
    "00000000009-1",
    "00000000005-9",
    "00000000006-7",
    "00000000007-5",
    "91850000007-3",
    "91850000008-1",
    "91850000003-2",
    "91850000004-0",
    "91850000001-6",
    "00000000002-6",
    "00000000014-1",
    "00000000001-8",
)


def qident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def table_exists(con, table_name: str) -> bool:
    return bool(
        con.execute(
            """
            select count(*) > 0
            from information_schema.tables
            where lower(table_name) = lower(?)
            """,
            [table_name],
        ).fetchone()[0]
    )


def columns(con, table_name: str) -> list[str]:
    if not table_exists(con, table_name):
        return []
    return [row[0] for row in con.execute(f"describe {qident(table_name)}").fetchall()]


def pick_column(available: Iterable[str], candidates: Iterable[str]) -> str | None:
    by_lower = {str(column).lower(): str(column) for column in available}
    for candidate in candidates:
        if str(candidate).lower() in by_lower:
            return by_lower[str(candidate).lower()]
    return None


def text_expr(column_name: str | None) -> str:
    if not column_name:
        return "null::varchar"
    return f"nullif(trim(cast({qident(column_name)} as varchar)), '')"


def timestamp_expr(column_name: str | None) -> str:
    if not column_name:
        return "null::timestamp"
    return f"try_cast({qident(column_name)} as timestamp)"


def _ensure_mapping_csv() -> None:
    if DUMMY_MAPPING_PATH.exists():
        return
    DUMMY_MAPPING_PATH.parent.mkdir(parents=True, exist_ok=True)
    with DUMMY_MAPPING_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["loco_no", "reason", "active_flag"],
            delimiter=";",
            lineterminator="\r\n",
        )
        writer.writeheader()
        for loco_no in DEFAULT_DUMMY_LOCOMOTIVES:
            writer.writerow(
                {
                    "loco_no": loco_no,
                    "reason": "Bekannte Planungs-/Dummy-Loknummer",
                    "active_flag": "Y",
                }
            )


def _read_mapping_rows() -> list[dict[str, str]]:
    _ensure_mapping_csv()
    rows: list[dict[str, str]] = []
    with DUMMY_MAPPING_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        for row in reader:
            loco_no = str(row.get("loco_no") or "").strip()
            active_flag = str(row.get("active_flag") or "Y").strip().upper()
            if not loco_no or active_flag in {"N", "NO", "FALSE", "0"}:
                continue
            rows.append(
                {
                    "loco_no": loco_no,
                    "reason": str(row.get("reason") or "Bekannte Planungs-/Dummy-Loknummer").strip(),
                }
            )
    return rows


def _raw_locomotive_movement_table(con) -> str | None:
    tables = [
        row[0]
        for row in con.execute(
            "select table_name from information_schema.tables where lower(table_name) like 'raw_%'"
        ).fetchall()
    ]
    for table in tables:
        if "locomotivemovement" in table.lower():
            return table
    return None


def build_dummy_locomotive_catalog(con) -> None:
    """Pflegbaren Katalog plus dynamische LocomotiveType-Erkennung aufbauen."""
    con.execute(
        """
        create or replace table cfg_dummy_locomotives_effective (
            loco_no varchar,
            match_reason varchar,
            catalog_source varchar
        )
        """
    )
    for row in _read_mapping_rows():
        con.execute(
            "insert into cfg_dummy_locomotives_effective values (?, ?, 'data/01_mapping/dummy_locomotives.csv')",
            [row["loco_no"], row["reason"]],
        )

    raw_table = _raw_locomotive_movement_table(con)
    if raw_table:
        available = columns(con, raw_table)
        loco_no = text_expr(pick_column(available, ["LocomotiveNo", "FirstLocomotiveNo", "Alias"]))
        locomotive_type = text_expr(pick_column(available, ["LocomotiveType"]))
        if loco_no != "null::varchar" and locomotive_type != "null::varchar":
            con.execute(
                f"""
                insert into cfg_dummy_locomotives_effective
                select distinct
                    {loco_no} as loco_no,
                    'LocomotiveType enthaelt Dummy: ' || coalesce({locomotive_type}, '') as match_reason,
                    '{raw_table}.LocomotiveType' as catalog_source
                from {qident(raw_table)}
                where {loco_no} is not null
                  and lower(coalesce({locomotive_type}, '')) like '%dummy%'
                """
            )

    con.execute(
        """
        create or replace table cfg_dummy_locomotives_effective as
        select
            loco_no,
            string_agg(distinct match_reason, ' | ' order by match_reason) as match_reason,
            string_agg(distinct catalog_source, ' | ' order by catalog_source) as catalog_source
        from cfg_dummy_locomotives_effective
        where nullif(trim(loco_no), '') is not null
        group by loco_no
        """
    )

    con.execute(
        """
        create or replace table audit_excluded_dummy_locomotives (
            source_table varchar,
            loco_no varchar,
            match_reason varchar,
            affected_rows bigint,
            affected_transports bigint,
            first_seen_utc timestamp,
            last_seen_utc timestamp
        )
        """
    )
    if raw_table:
        available = columns(con, raw_table)
        loco_no = text_expr(pick_column(available, ["LocomotiveNo", "FirstLocomotiveNo", "Alias"]))
        transport = text_expr(pick_column(available, ["TransportNumber", "TransportNo", "TransportId", "TransportID"]))
        departure = timestamp_expr(pick_column(available, ["ActualDeparture", "LocomotiveActualDeparture"]))
        arrival = timestamp_expr(pick_column(available, ["ActualArrival", "LocomotiveActualArrival"]))
        if loco_no != "null::varchar":
            con.execute(
                f"""
                insert into audit_excluded_dummy_locomotives
                select
                    '{raw_table}',
                    d.loco_no,
                    d.match_reason,
                    count(*),
                    count(distinct {transport}),
                    min(coalesce({departure}, {arrival})),
                    max(coalesce({arrival}, {departure}))
                from {qident(raw_table)} r
                join cfg_dummy_locomotives_effective d
                  on d.loco_no = {loco_no}
                group by d.loco_no, d.match_reason
                """
            )

    count = con.execute("select count(*) from cfg_dummy_locomotives_effective").fetchone()[0]
    print(f"Dummy-Lok-Katalog aufgebaut: {count} bekannte oder dynamisch erkannte Loknummern.")


def exclude_dummy_locomotives_from_staging(con) -> None:
    """Dummy-Loks vor Core, Timeline, GAP, Gate und Export aus dem Staging entfernen."""
    if not table_exists(con, "stg_loco_events"):
        raise RuntimeError("stg_loco_events fehlt. Dummy-Ausschluss kann nicht ausgefuehrt werden.")
    con.execute(
        """
        create or replace table audit_excluded_dummy_locomotive_staging as
        select
            e.source_table,
            e.source_row_id,
            e.loco_no,
            e.transport_number,
            e.actual_departure_ts,
            e.actual_arrival_ts,
            d.match_reason,
            d.catalog_source
        from stg_loco_events e
        join cfg_dummy_locomotives_effective d
          on d.loco_no = e.loco_no
        """
    )
    if table_exists(con, "stg_loco_events_skipped"):
        con.execute(
            """
            insert into stg_loco_events_skipped(source_table, source_row_id, skip_reason)
            select
                source_table,
                source_row_id,
                'Planungs-/Dummy-Lok ausgeschlossen: ' || coalesce(match_reason, 'Katalogtreffer')
            from audit_excluded_dummy_locomotive_staging
            """
        )
    removed = con.execute("select count(*) from audit_excluded_dummy_locomotive_staging").fetchone()[0]
    con.execute(
        """
        delete from stg_loco_events e
        where exists (
            select 1
            from cfg_dummy_locomotives_effective d
            where d.loco_no = e.loco_no
        )
        """
    )
    print(f"Dummy-Loks vor Timeline ausgeschlossen: {removed} Staging-Zeilen.")


def _cutoff_utc(con):
    if not table_exists(con, "dq_run_metadata"):
        return None
    cols = {column.lower() for column in columns(con, "dq_run_metadata")}
    if "error_cutoff_utc" not in cols:
        return None
    return con.execute("select max(try_cast(error_cutoff_utc as timestamp)) from dq_run_metadata").fetchone()[0]


def consolidate_dummy_locomotive_findings(con, run_id: str) -> None:
    """Normale Dummy-Findings entfernen und pro Lok/Transport genau R012 erzeugen."""
    if not table_exists(con, "dq_findings"):
        raise RuntimeError("dq_findings fehlt. Dummy-Findings koennen nicht konsolidiert werden.")
    cutoff = _cutoff_utc(con)
    if cutoff is None:
        raise RuntimeError("dq_run_metadata.error_cutoff_utc fehlt. Dummy-Findings brechen sicher ab.")

    con.execute(
        """
        delete from dq_findings f
        where exists (
            select 1 from cfg_dummy_locomotives_effective d where d.loco_no = f.loco_no
        )
        """
    )

    raw_table = _raw_locomotive_movement_table(con)
    if not raw_table:
        return
    available = columns(con, raw_table)
    loco_no = text_expr(pick_column(available, ["LocomotiveNo", "FirstLocomotiveNo", "Alias"]))
    transport = text_expr(pick_column(available, ["TransportNumber", "TransportNo", "TransportId", "TransportID"]))
    performing_ru = text_expr(
        pick_column(
            available,
            [
                "CurrentContractant",
                "CALPerformingRU",
                "PerformingRU",
                "PerformingRailwayUndertaking",
                "RailwayUndertaking",
                "Carrier",
                "ProductionCompany",
            ],
        )
    )
    departure = timestamp_expr(pick_column(available, ["ActualDeparture", "LocomotiveActualDeparture"]))
    arrival = timestamp_expr(pick_column(available, ["ActualArrival", "LocomotiveActualArrival"]))
    origin_country = text_expr(
        pick_column(
            available,
            [
                "OriginCountryISO",
                "OriginCountryIso",
                "OriginCountry",
                "FromCountryISO",
                "FromCountry",
                "DepartureCountryISO",
                "DepartureCountry",
                "Country",
            ],
        )
    )
    destination_country = text_expr(
        pick_column(
            available,
            [
                "DestinationCountryISO",
                "DestinationCountryIso",
                "DestinationCountry",
                "ToCountryISO",
                "ToCountry",
                "ArrivalCountryISO",
                "ArrivalCountry",
                "Country",
            ],
        )
    )
    if loco_no == "null::varchar":
        return

    con.execute(
        f"""
        insert into dq_findings (
            run_id, severity, rule_id, rule_group, loco_no, transport_number,
            performing_ru, row_type, movement_sequence_no, period_start_utc,
            period_end_utc, message, suggested_action, status, source_table,
            source_row_id, overlap_with_transport_number
        )
        with raw_rows as (
            select
                row_number() over () as source_row_id,
                {loco_no} as loco_no,
                {transport} as transport_number,
                {performing_ru} as performing_ru,
                {departure} as period_start_utc,
                {arrival} as period_end_utc,
                upper(coalesce({origin_country}, '')) = 'DE'
                  or upper(coalesce({destination_country}, '')) = 'DE' as is_de_relevant
            from {qident(raw_table)}
        ), grouped as (
            select
                r.loco_no,
                r.transport_number,
                max(r.performing_ru) as performing_ru,
                min(r.period_start_utc) as period_start_utc,
                max(r.period_end_utc) as period_end_utc,
                min(r.source_row_id) as source_row_id,
                count(*) as affected_raw_rows,
                max(d.match_reason) as match_reason
            from raw_rows r
            join cfg_dummy_locomotives_effective d on d.loco_no = r.loco_no
            where r.is_de_relevant
              and coalesce(r.period_start_utc, r.period_end_utc) is not null
              and coalesce(r.period_start_utc, r.period_end_utc) <= ?
            group by r.loco_no, r.transport_number
        )
        select
            ?, 'ERROR', 'R012', 'NO_LOCO_RAW', loco_no, transport_number,
            performing_ru, 'RAW_DUMMY_LOCOMOTIVE', null::bigint,
            period_start_utc, period_end_utc,
            'Planungs-/Dummy-Lok erkannt und aus fachlicher Verarbeitung ausgeschlossen. Grund: '
              || coalesce(match_reason, 'Katalogtreffer')
              || '. Betroffene Rohdatenzeilen: ' || cast(affected_raw_rows as varchar) || '.',
            'Echte Loknummer beziehungsweise Planung in RailCube pruefen und korrigieren.',
            'open', '{raw_table}', source_row_id, null::varchar
        from grouped
        """,
        [cutoff, str(run_id)],
    )
    count = con.execute(
        "select count(*) from dq_findings where rule_id = 'R012' and row_type = 'RAW_DUMMY_LOCOMOTIVE'"
    ).fetchone()[0]
    print(f"Dummy-R012-Findings konsolidiert: {count} Lok-/Transport-Faelle.")
