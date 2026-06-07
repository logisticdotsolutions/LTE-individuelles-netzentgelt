from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Iterable

import duckdb

# NETZENTGELT_REST_EXPORT_PHASE4_V1_20260607
# Sichtbare Hauptgruppen in der Fachoberfläche. Alle weiteren PerformingRUs
# werden gesammelt unter "Rest" ausgewiesen und bleiben einzeln exportierbar.
PRIMARY_EXPORT_GROUPS = {
    "LTE_DE": {
        "title": "LTE DE",
        "file_label": "LTE_DE",
        "performing_ru_values": (
            "LTE DE - LTE Germany GmbH",
            "LTE Germany GmbH",
        ),
    },
    "LTE_NL": {
        "title": "LTE NL",
        "file_label": "LTE_NL",
        "performing_ru_values": (
            "LTE NL - LTE Netherlands B.V.",
        ),
    },
}


def _qident(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def _table_exists(con, table_name: str) -> bool:
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


def _columns(con, table_name: str) -> list[str]:
    return [row[0] for row in con.execute(f"describe {_qident(table_name)}").fetchall()]


def _pick_column(columns: Iterable[str], candidates: Iterable[str]) -> str | None:
    by_lower = {str(column).lower(): str(column) for column in columns}
    for candidate in candidates:
        if str(candidate).lower() in by_lower:
            return by_lower[str(candidate).lower()]
    return None


def _placeholders(values: Iterable[object]) -> str:
    values = tuple(values)
    if not values:
        raise ValueError("Mindestens ein Wert ist erforderlich.")
    return ", ".join("?" for _ in values)


def _to_day_bounds(date_from: date, date_to: date) -> tuple[datetime, datetime]:
    if date_from > date_to:
        raise ValueError("Das Von-Datum darf nicht nach dem Bis-Datum liegen.")
    return (
        datetime.combine(date_from, time.min),
        datetime.combine(date_to + timedelta(days=1), time.min),
    )


def primary_performing_ru_values() -> tuple[str, ...]:
    result: list[str] = []
    for config in PRIMARY_EXPORT_GROUPS.values():
        for value in config["performing_ru_values"]:
            cleaned = str(value).strip()
            if cleaned and cleaned not in result:
                result.append(cleaned)
    return tuple(result)


def _build_order_owner_cte(con) -> tuple[str, str, str]:
    """
    Optionale OrderOwner-Auflösung bereitstellen.

    Priorität:
    1. order_owner direkt in core_loco_timeline, falls künftig vorhanden.
    2. OrderOwner aus raw_transportdetail über TransportNumber aggregieren.
    3. Verständlicher Fallback "Nicht verfügbar".

    Mehrere OrderOwner für dieselbe TransportNumber werden sichtbar zusammengeführt,
    damit keine vermeintliche Eindeutigkeit erzeugt wird.
    """
    core_columns = _columns(con, "core_loco_timeline")
    core_order_owner = _pick_column(
        core_columns,
        ["order_owner", "OrderOwner", "ClientOrderOwner"],
    )

    if core_order_owner:
        return (
            "",
            "",
            f"coalesce(nullif(trim(cast(c.{_qident(core_order_owner)} as varchar)), ''), 'Nicht verfügbar')",
        )

    if not _table_exists(con, "raw_transportdetail"):
        return ("", "", "'Nicht verfügbar'")

    td_columns = _columns(con, "raw_transportdetail")
    td_transport = _pick_column(
        td_columns,
        ["TransportNumber", "TransportNo", "TransportId", "TransportID"],
    )
    td_order_owner = _pick_column(
        td_columns,
        ["OrderOwner", "ClientOrderOwner", "OrderOwnerName", "OrderOwnerCompany"],
    )

    if not td_transport or not td_order_owner:
        return ("", "", "'Nicht verfügbar'")

    transport_expr = f"nullif(trim(cast({_qident(td_transport)} as varchar)), '')"
    owner_expr = f"nullif(trim(cast({_qident(td_order_owner)} as varchar)), '')"

    cte = f"""
        order_owner_by_transport as (
            select
                {transport_expr} as transport_number,
                case
                    when count(distinct {owner_expr}) = 0 then null
                    when count(distinct {owner_expr}) = 1 then max({owner_expr})
                    else string_agg(distinct {owner_expr}, ' | ' order by {owner_expr})
                end as order_owner
            from raw_transportdetail
            where {transport_expr} is not null
            group by {transport_expr}
        ),
    """
    join_sql = "left join order_owner_by_transport oo on oo.transport_number = c.transport_number"
    owner_sql = "coalesce(nullif(trim(cast(oo.order_owner as varchar)), ''), 'Nicht verfügbar')"
    return cte, join_sql, owner_sql


def list_rest_export_overview(
    db_path: Path,
    date_from: date,
    date_to: date,
) -> list[dict[str, object]]:
    """
    Alle DE-relevanten Bewegungszeilen außerhalb LTE DE und LTE NL ausweisen.

    Die Liste dient der transparenten Restkontrolle. Sie zeigt je PerformingRU
    und optional je OrderOwner, wie viele Zeilen betroffen, exportfähig oder
    blockiert sind. Downloads bleiben bewusst RU-spezifisch, weil die offizielle
    XLSX-Vorlage Marktpartner-Kopfdaten je RU erwartet.
    """
    db_path = Path(db_path)
    if not db_path.exists():
        return []

    primary_values = primary_performing_ru_values()
    window_start, window_end_exclusive = _to_day_bounds(date_from, date_to)

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        if not _table_exists(con, "core_loco_timeline"):
            return []

        core_columns = _columns(con, "core_loco_timeline")
        timestamp_col = _pick_column(
            core_columns,
            ["actual_departure_ts", "period_start_utc", "sequence_ts"],
        )
        if not timestamp_col:
            raise RuntimeError(
                "Rest-Auswertung nicht möglich: In core_loco_timeline fehlt eine geeignete Zeitspalte."
            )

        order_owner_cte, order_owner_join, order_owner_sql = _build_order_owner_cte(con)
        primary_placeholders = _placeholders(primary_values)
        timestamp_sql = f"c.{_qident(timestamp_col)}"

        rows = con.execute(
            f"""
            with
            {order_owner_cte}
            rest_rows as (
                select
                    trim(cast(c.performing_ru as varchar)) as performing_ru,
                    {order_owner_sql} as order_owner,
                    c.loco_no,
                    c.transport_number,
                    coalesce(c.export_ready, false) as export_ready
                from core_loco_timeline c
                {order_owner_join}
                where c.row_type = 'MOVEMENT'
                  and c.report_scope = 'IN_REPORT'
                  and nullif(trim(cast(c.performing_ru as varchar)), '') is not null
                  and {timestamp_sql} >= ?
                  and {timestamp_sql} < ?
                  and trim(cast(c.performing_ru as varchar)) not in ({primary_placeholders})
            )
            select
                performing_ru,
                order_owner,
                count(*) as affected_rows,
                sum(case when export_ready then 1 else 0 end) as export_ready_rows,
                sum(case when not export_ready then 1 else 0 end) as blocked_rows,
                count(distinct nullif(trim(cast(loco_no as varchar)), '')) as affected_locomotives,
                count(distinct nullif(trim(cast(transport_number as varchar)), '')) as affected_transports
            from rest_rows
            group by performing_ru, order_owner
            order by performing_ru, order_owner
            """,
            [window_start, window_end_exclusive, *primary_values],
        ).fetchall()

        return [
            {
                "PerformingRU": row[0],
                "OrderOwner": row[1],
                "Betroffene Bewegungszeilen": int(row[2] or 0),
                "Davon exportfähig": int(row[3] or 0),
                "Davon gesperrt": int(row[4] or 0),
                "Betroffene Loks": int(row[5] or 0),
                "Betroffene Transporte": int(row[6] or 0),
            }
            for row in rows
        ]
    finally:
        con.close()
