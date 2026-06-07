"""
Netzentgelt MVP - kontrollierte manuelle Overrides mit Audit Trail
==================================================================

Phase 5A ergänzt eine fachlich kontrollierte Korrekturschicht. Die Rohdateien
unter data/00_raw bleiben unverändert. Bestätigte Korrekturen werden in
``data/01_mapping/manual_overrides.csv`` gespeichert und bei jedem Neuaufbau
auf die temporär importierten DuckDB-Rohdaten angewandt.

Unterstützte Korrekturen
------------------------
- SET_LOCO_NO:             Loknummer ergänzen oder korrigieren
- SET_PERFORMING_RU:       nutzendes EVU ergänzen oder korrigieren
- SET_ACTUAL_DEPARTURE:    ActualDeparture korrigieren
- SET_ACTUAL_ARRIVAL:      ActualArrival korrigieren
- SET_SEQUENCE_TS:         fachlichen Grenzzeitanker korrigieren
- CLASSIFY_GAP:            fachliche Klassifikation dokumentieren, noch ohne
                           automatische Änderung des Export-Gates
- CASE_NOTE:               reine Bearbeitungsnotiz dokumentieren

Sicherheitsprinzip
-----------------
- Original-CSVs werden niemals überschrieben.
- Widersprüchliche aktive Overrides brechen den Pipeline-Lauf verständlich ab.
- Jede Anwendung wird in audit_manual_override_application protokolliert.
- Fachliche GAP-Klassifikationen werden zunächst nur dokumentiert. Eine spätere
  Freigabelogik darf erst nach verbindlicher Festlegung der Grenzwerte folgen.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


PHASE5A_MARKER = "NETZENTGELT_MANUAL_OVERRIDE_PHASE5A_V1_20260607"
ROOT = Path(__file__).resolve().parents[1]
MAP_DIR = ROOT / "data" / "01_mapping"
MANUAL_OVERRIDE_PATH = MAP_DIR / "manual_overrides.csv"

OVERRIDE_COLUMNS = (
    "override_id",
    "active_flag",
    "override_type",
    "transport_number",
    "target_loco_no",
    "target_actual_departure_utc",
    "target_actual_arrival_utc",
    "target_source_table",
    "target_source_row_id",
    "override_value",
    "classification_code",
    "comment",
    "created_by",
    "created_at_utc",
    "updated_at_utc",
)

SUPPORTED_RAW_TYPES = {
    "SET_LOCO_NO",
    "SET_PERFORMING_RU",
    "SET_ACTUAL_DEPARTURE",
    "SET_ACTUAL_ARRIVAL",
}
SUPPORTED_STAGING_TYPES = {"SET_SEQUENCE_TS"}
DOCUMENT_ONLY_TYPES = {"CLASSIFY_GAP", "CASE_NOTE"}
SUPPORTED_TYPES = SUPPORTED_RAW_TYPES | SUPPORTED_STAGING_TYPES | DOCUMENT_ONLY_TYPES


class ManualOverrideError(RuntimeError):
    """Verständlicher Abbruch bei unsicheren oder widersprüchlichen Overrides."""


def utc_now_text() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_manual_override_csv() -> Path:
    """Persistente Override-Datei mit stabilem Schema anlegen, falls sie fehlt."""
    MAP_DIR.mkdir(parents=True, exist_ok=True)

    if not MANUAL_OVERRIDE_PATH.exists():
        with MANUAL_OVERRIDE_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=OVERRIDE_COLUMNS, delimiter=";")
            writer.writeheader()

    return MANUAL_OVERRIDE_PATH


def qident(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def table_exists(con, table_name: str) -> bool:
    return (
        con.execute(
            """
            select count(*)
            from information_schema.tables
            where lower(table_name) = lower(?)
            """,
            [table_name],
        ).fetchone()[0]
        > 0
    )


def columns(con, table_name: str) -> list[str]:
    return [row[0] for row in con.execute(f"describe {qident(table_name)}").fetchall()]


def pick_column(available_columns: Iterable[str], candidates: Iterable[str]) -> str | None:
    by_lower = {str(column).lower(): str(column) for column in available_columns}
    for candidate in candidates:
        if str(candidate).lower() in by_lower:
            return by_lower[str(candidate).lower()]
    return None


def _normalize_override_type(value: object) -> str:
    return str(value or "").strip().upper()


def _clean(value: object) -> str:
    return str(value or "").strip()


def _ensure_audit_table(con) -> None:
    con.execute(
        """
        create or replace table audit_manual_override_application (
            run_id varchar,
            override_id varchar,
            override_type varchar,
            phase varchar,
            application_status varchar,
            affected_rows bigint,
            transport_number varchar,
            target_loco_no varchar,
            override_value varchar,
            classification_code varchar,
            comment varchar,
            created_by varchar,
            created_at_utc varchar,
            applied_at_utc timestamp,
            application_message varchar
        )
        """
    )


def _audit(
    con,
    *,
    run_id: str,
    row: dict[str, object],
    phase: str,
    status: str,
    affected_rows: int,
    message: str,
) -> None:
    con.execute(
        """
        insert into audit_manual_override_application values (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, current_timestamp, ?
        )
        """,
        [
            str(run_id),
            _clean(row.get("override_id")),
            _normalize_override_type(row.get("override_type")),
            phase,
            status,
            int(affected_rows or 0),
            _clean(row.get("transport_number")) or None,
            _clean(row.get("target_loco_no")) or None,
            _clean(row.get("override_value")) or None,
            _clean(row.get("classification_code")) or None,
            _clean(row.get("comment")) or None,
            _clean(row.get("created_by")) or None,
            _clean(row.get("created_at_utc")) or None,
            message,
        ],
    )


def import_manual_overrides(con) -> None:
    """Persistente Override-Datei importieren und Konflikte früh erkennen."""
    override_path = ensure_manual_override_csv()

    con.execute(
        """
        create or replace table cfg_manual_overrides as
        select *
        from read_csv_auto(
            ?,
            delim=';',
            header=true,
            all_varchar=true,
            ignore_errors=false,
            union_by_name=true
        )
        """,
        [str(override_path)],
    )

    # Defensiv fehlende Spalten ergänzen, falls eine ältere Datei übernommen wird.
    existing = {column.lower() for column in columns(con, "cfg_manual_overrides")}
    for required in OVERRIDE_COLUMNS:
        if required.lower() not in existing:
            con.execute(
                f"alter table cfg_manual_overrides add column {qident(required)} varchar"
            )

    con.execute(
        """
        create or replace table dq_manual_override_conflicts as
        with active_rows as (
            select
                *,
                upper(trim(coalesce(active_flag, 'Y'))) as active_flag_norm,
                upper(trim(coalesce(override_type, ''))) as override_type_norm
            from cfg_manual_overrides
        )
        select
            override_type_norm as override_type,
            nullif(trim(transport_number), '') as transport_number,
            nullif(trim(target_loco_no), '') as target_loco_no,
            nullif(trim(target_actual_departure_utc), '') as target_actual_departure_utc,
            nullif(trim(target_actual_arrival_utc), '') as target_actual_arrival_utc,
            count(*) as active_override_rows,
            count(distinct nullif(trim(override_value), '')) as distinct_override_values,
            string_agg(distinct override_id, ' | ' order by override_id) as override_ids,
            string_agg(distinct nullif(trim(override_value), ''), ' | ' order by nullif(trim(override_value), ''))
                as override_values
        from active_rows
        where active_flag_norm not in ('N', 'NO', 'FALSE', '0')
          and override_type_norm in (
                'SET_LOCO_NO',
                'SET_PERFORMING_RU',
                'SET_ACTUAL_DEPARTURE',
                'SET_ACTUAL_ARRIVAL',
                'SET_SEQUENCE_TS'
          )
        group by
            override_type_norm,
            nullif(trim(transport_number), ''),
            nullif(trim(target_loco_no), ''),
            nullif(trim(target_actual_departure_utc), ''),
            nullif(trim(target_actual_arrival_utc), '')
        having count(distinct nullif(trim(override_value), '')) > 1
        """
    )

    conflict_count = int(
        con.execute("select count(*) from dq_manual_override_conflicts").fetchone()[0]
    )

    if conflict_count > 0:
        raise ManualOverrideError(
            "Widersprüchliche aktive manuelle Overrides erkannt. "
            "Bitte data/01_mapping/manual_overrides.csv prüfen und ältere Einträge deaktivieren. "
            f"Konfliktgruppen: {conflict_count}."
        )

    con.execute(
        """
        create or replace table cfg_manual_overrides_effective as
        select *
        from cfg_manual_overrides
        where upper(trim(coalesce(active_flag, 'Y'))) not in ('N', 'NO', 'FALSE', '0')
        """
    )

    _ensure_audit_table(con)

    active_count = int(
        con.execute("select count(*) from cfg_manual_overrides_effective").fetchone()[0]
    )
    print(f"Manuelle Overrides importiert: {active_count} aktive Einträge.")


def _effective_rows(con) -> list[dict[str, object]]:
    if not table_exists(con, "cfg_manual_overrides_effective"):
        return []

    result = con.execute("select * from cfg_manual_overrides_effective").fetchall()
    names = columns(con, "cfg_manual_overrides_effective")
    return [dict(zip(names, row)) for row in result]


def _where_for_raw(
    *,
    table_columns: list[str],
    row: dict[str, object],
    transport_column: str | None,
    loco_column: str | None,
    actual_departure_column: str | None,
    for_loco_assignment: bool = False,
) -> tuple[str | None, list[object], str | None]:
    conditions: list[str] = []
    params: list[object] = []

    transport_number = _clean(row.get("transport_number"))
    target_loco_no = _clean(row.get("target_loco_no"))
    target_actual_departure = _clean(row.get("target_actual_departure_utc"))

    if transport_number:
        if not transport_column:
            return None, [], "TransportNumber-Spalte fehlt in der Zieltabelle."
        conditions.append(f"nullif(trim(cast({qident(transport_column)} as varchar)), '') = ?")
        params.append(transport_number)

    if target_actual_departure:
        if not actual_departure_column:
            return None, [], "ActualDeparture-Spalte fehlt in der Zieltabelle."
        conditions.append(
            f"try_cast({qident(actual_departure_column)} as timestamp) = try_cast(? as timestamp)"
        )
        params.append(target_actual_departure)

    if loco_column:
        if target_loco_no:
            conditions.append(f"nullif(trim(cast({qident(loco_column)} as varchar)), '') = ?")
            params.append(target_loco_no)
        elif for_loco_assignment:
            conditions.append(
                "(nullif(trim(cast(" + qident(loco_column) + " as varchar)), '') is null "
                "or trim(cast(" + qident(loco_column) + " as varchar)) = '00000000000-0')"
            )

    if not conditions:
        return None, [], "Kein ausreichend eindeutiges Zielkriterium vorhanden."

    return " and ".join(conditions), params, None


def _update_raw_table(
    con,
    *,
    run_id: str,
    row: dict[str, object],
    table_name: str,
    value_candidates: list[str],
    phase: str,
    for_loco_assignment: bool = False,
) -> int:
    if not table_exists(con, table_name):
        _audit(
            con,
            run_id=run_id,
            row=row,
            phase=phase,
            status="SKIPPED",
            affected_rows=0,
            message=f"Zieltabelle {table_name} fehlt.",
        )
        return 0

    table_columns = columns(con, table_name)
    value_column = pick_column(table_columns, value_candidates)
    transport_column = pick_column(
        table_columns,
        ["TransportNumber", "TransportNo", "TransportId", "TransportID"],
    )
    loco_column = pick_column(table_columns, ["LocomotiveNo", "FirstLocomotiveNo", "Alias"])
    departure_column = pick_column(
        table_columns,
        ["ActualDeparture", "LocomotiveActualDeparture"],
    )

    if not value_column:
        _audit(
            con,
            run_id=run_id,
            row=row,
            phase=phase,
            status="SKIPPED",
            affected_rows=0,
            message=f"Keine passende Zielspalte in {table_name} gefunden.",
        )
        return 0

    where_sql, params, error = _where_for_raw(
        table_columns=table_columns,
        row=row,
        transport_column=transport_column,
        loco_column=loco_column,
        actual_departure_column=departure_column,
        for_loco_assignment=for_loco_assignment,
    )

    if error or not where_sql:
        _audit(
            con,
            run_id=run_id,
            row=row,
            phase=phase,
            status="SKIPPED",
            affected_rows=0,
            message=error or "Unsicheres Zielkriterium.",
        )
        return 0

    override_value = _clean(row.get("override_value"))
    if not override_value:
        _audit(
            con,
            run_id=run_id,
            row=row,
            phase=phase,
            status="SKIPPED",
            affected_rows=0,
            message="Override-Wert fehlt.",
        )
        return 0

    affected = int(
        con.execute(
            f"select count(*) from {qident(table_name)} where {where_sql}",
            params,
        ).fetchone()[0]
    )

    if affected > 0:
        con.execute(
            f"update {qident(table_name)} set {qident(value_column)} = ? where {where_sql}",
            [override_value, *params],
        )

    _audit(
        con,
        run_id=run_id,
        row=row,
        phase=phase,
        status="APPLIED" if affected > 0 else "NO_MATCH",
        affected_rows=affected,
        message=(
            f"{table_name}.{value_column} aktualisiert."
            if affected > 0
            else f"Kein passender Datensatz in {table_name} gefunden."
        ),
    )
    return affected


def apply_raw_manual_overrides(con, run_id: str) -> None:
    """Korrekturen vor Bildung von Staging, Timeline und Findings anwenden."""
    if not table_exists(con, "cfg_manual_overrides_effective"):
        import_manual_overrides(con)

    for row in _effective_rows(con):
        override_type = _normalize_override_type(row.get("override_type"))

        if override_type == "SET_LOCO_NO":
            # Beide Quellen aktualisieren: LocomotiveMovement für die Timeline und
            # TransportDetail für die verdichtete R012-Prüfung.
            _update_raw_table(
                con,
                run_id=run_id,
                row=row,
                table_name="raw_locomotivemovement",
                value_candidates=["LocomotiveNo", "FirstLocomotiveNo", "Alias"],
                phase="RAW_LOCOMOTIVE_MOVEMENT",
                for_loco_assignment=True,
            )
            _update_raw_table(
                con,
                run_id=run_id,
                row=row,
                table_name="raw_transportdetail",
                value_candidates=["FirstLocomotiveNo"],
                phase="RAW_TRANSPORT_DETAIL",
                for_loco_assignment=True,
            )

        elif override_type == "SET_PERFORMING_RU":
            _update_raw_table(
                con,
                run_id=run_id,
                row=row,
                table_name="raw_locomotivemovement",
                value_candidates=[
                    "CurrentContractant",
                    "CALPerformingRU",
                    "PerformingRU",
                    "PerformingRailwayUndertaking",
                    "RailwayUndertaking",
                    "Carrier",
                    "ProductionCompany",
                ],
                phase="RAW_LOCOMOTIVE_MOVEMENT",
            )

        elif override_type == "SET_ACTUAL_DEPARTURE":
            _update_raw_table(
                con,
                run_id=run_id,
                row=row,
                table_name="raw_locomotivemovement",
                value_candidates=["ActualDeparture", "LocomotiveActualDeparture"],
                phase="RAW_LOCOMOTIVE_MOVEMENT",
            )

        elif override_type == "SET_ACTUAL_ARRIVAL":
            _update_raw_table(
                con,
                run_id=run_id,
                row=row,
                table_name="raw_locomotivemovement",
                value_candidates=["ActualArrival", "LocomotiveActualArrival"],
                phase="RAW_LOCOMOTIVE_MOVEMENT",
            )

        elif override_type in SUPPORTED_STAGING_TYPES:
            # Wird bewusst erst nach build_loco_events() verarbeitet.
            continue

        elif override_type in DOCUMENT_ONLY_TYPES:
            _audit(
                con,
                run_id=run_id,
                row=row,
                phase="DOCUMENTATION",
                status="DOCUMENTED_ONLY",
                affected_rows=0,
                message=(
                    "Fachliche Dokumentation gespeichert. Keine automatische Änderung "
                    "des Export-Gates in Phase 5A."
                ),
            )

        else:
            _audit(
                con,
                run_id=run_id,
                row=row,
                phase="VALIDATION",
                status="SKIPPED",
                affected_rows=0,
                message=f"Nicht unterstützter Override-Typ: {override_type or '-'}.",
            )


def apply_staging_manual_overrides(con, run_id: str) -> None:
    """Grenzzeitanker nach Staging-Bildung, aber vor Timeline-Bildung korrigieren."""
    if not table_exists(con, "stg_loco_events"):
        return

    staging_columns = columns(con, "stg_loco_events")
    required_columns = {
        "sequence_ts",
        "sequence_ts_source",
        "sequence_ts_reason",
        "transport_number",
        "loco_no",
        "actual_departure_ts",
    }
    if not required_columns.issubset({column.lower() for column in staging_columns}):
        return

    for row in _effective_rows(con):
        override_type = _normalize_override_type(row.get("override_type"))
        if override_type != "SET_SEQUENCE_TS":
            continue

        conditions: list[str] = []
        params: list[object] = []
        transport_number = _clean(row.get("transport_number"))
        target_loco_no = _clean(row.get("target_loco_no"))
        target_actual_departure = _clean(row.get("target_actual_departure_utc"))
        target_source_row_id = _clean(row.get("target_source_row_id"))
        override_value = _clean(row.get("override_value"))

        if transport_number:
            conditions.append("nullif(trim(cast(transport_number as varchar)), '') = ?")
            params.append(transport_number)
        if target_loco_no:
            conditions.append("nullif(trim(cast(loco_no as varchar)), '') = ?")
            params.append(target_loco_no)
        if target_actual_departure:
            conditions.append("actual_departure_ts = try_cast(? as timestamp)")
            params.append(target_actual_departure)
        if target_source_row_id:
            conditions.append("source_row_id = try_cast(? as bigint)")
            params.append(target_source_row_id)

        if not conditions or not override_value:
            _audit(
                con,
                run_id=run_id,
                row=row,
                phase="STAGING_LOCO_EVENTS",
                status="SKIPPED",
                affected_rows=0,
                message="Grenzzeitanker-Override ohne ausreichend eindeutiges Ziel oder ohne Wert.",
            )
            continue

        where_sql = " and ".join(conditions)
        affected = int(
            con.execute(
                f"select count(*) from stg_loco_events where {where_sql}",
                params,
            ).fetchone()[0]
        )

        if affected > 0:
            con.execute(
                f"""
                update stg_loco_events
                set
                    sequence_ts = try_cast(? as timestamp),
                    sequence_ts_source = 'MANUAL_OVERRIDE',
                    sequence_ts_reason = 'Manueller fachlicher Grenzzeitanker aus cfg_manual_overrides.'
                where {where_sql}
                """,
                [override_value, *params],
            )

        _audit(
            con,
            run_id=run_id,
            row=row,
            phase="STAGING_LOCO_EVENTS",
            status="APPLIED" if affected > 0 else "NO_MATCH",
            affected_rows=affected,
            message=(
                "sequence_ts im Staging aktualisiert."
                if affected > 0
                else "Kein passendes Staging-Ereignis gefunden."
            ),
        )
