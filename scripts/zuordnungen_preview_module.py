from __future__ import annotations

from datetime import date
from io import BytesIO
from pathlib import Path

import duckdb
import pandas as pd

from export_module import _to_day_bounds, table_exists
from zuordnungen_export_module import _holding_holder_filter_sql


PREVIEW_COLUMNS = (
    "TfzE oder tEns*",
    "Beginn der Zuordnung*",
    "Ende der Zuordnung",
    "Nutzer-vEns*",
    "Marktpartner ID für Nutzungsüberlassung",
    "PerformingRU",
    "Exportstatus",
    "Hinweis",
)


def build_zuordnungen_holding_preview(
    *,
    db_path: Path,
    date_from: date,
    date_to: date,
) -> pd.DataFrame:
    """
    Z01-Vorschau inklusive blockierter Zeilen nur für Halter = LTE Holding erzeugen.

    Die Vorschau ist bewusst unabhängig vom Download-Gate. So kann ein
    Fachanwender bereits vor der Fehlerbehebung sehen, welche LTE-Holding-
    Haltersegmente nach Klärung der Prüffälle in die beiden Holding-Dateien
    einfließen würden.
    """
    db_path = Path(db_path)

    if not db_path.exists():
        raise FileNotFoundError(f"DuckDB-Datei fehlt: {db_path}")

    window_start, window_end_exclusive = _to_day_bounds(date_from, date_to)
    con = duckdb.connect(str(db_path), read_only=True)

    try:
        required_tables = [
            "core_usage_assignment_segments",
            "core_usage_assignment_segment_movements",
        ]
        missing_tables = [
            table_name
            for table_name in required_tables
            if not table_exists(con, table_name)
        ]

        if missing_tables:
            raise RuntimeError(
                "Vorschau nicht möglich. Fehlende Tabellen: "
                + ", ".join(missing_tables)
            )

        gate_ru_ready = table_exists(con, "dq_export_gate_ru")
        global_gate_ready = table_exists(con, "dq_global_export_blockers")

        local_blocked_sql = "false"
        if gate_ru_ready:
            local_blocked_sql = """
                exists (
                    select 1
                    from dq_export_gate_ru g
                    where g.loco_no = s.loco_no
                      and g.performing_ru is not distinct from s.performing_ru
                      and g.coverage_date >= cast(s.segment_start_utc as date)
                      and g.coverage_date <= cast(s.segment_end_utc as date)
                      and g.gate_status = 'BLOCKED'
                )
            """

        global_blocked_sql = "false"
        if global_gate_ready:
            global_blocked_sql = """
                exists (
                    select 1
                    from dq_global_export_blockers b
                    where b.blocker_date >= cast(s.segment_start_utc as date)
                      and b.blocker_date <= cast(s.segment_end_utc as date)
                      and b.gate_status = 'BLOCKED'
                )
            """

        gates_ready = gate_ru_ready and global_gate_ready
        status_sql = (
            f"""
            case
                when coalesce(s.export_blocking_movement_rows, 0) > 0
                  or ({local_blocked_sql})
                  or ({global_blocked_sql})
                    then 'BLOCKIERT'
                else 'EXPORTFÄHIG'
            end
            """
            if gates_ready
            else "'PRÜFUNG NICHT VERFÜGBAR'"
        )

        hint_sql = (
            f"""
            case
                when coalesce(s.export_blocking_movement_rows, 0) > 0
                    then 'Segment enthält blockierende Bewegungszeilen.'
                when ({local_blocked_sql})
                    then 'Für Lok und nutzendes EVU bestehen blockierende Prüffälle.'
                when ({global_blocked_sql})
                    then 'Im Zeitraum besteht ein globaler Exportblocker.'
                else ''
            end
            """
            if gates_ready
            else "'Export-Gate-Tabellen fehlen. Pipeline neu ausführen.'"
        )

        rows = con.execute(
            f"""
            select
                cast(s.loco_no as varchar) as "TfzE oder tEns*",
                s.segment_start_utc as "Beginn der Zuordnung*",
                s.segment_end_utc as "Ende der Zuordnung",
                coalesce(nullif(s.user_vens, ''), s.performing_ru) as "Nutzer-vEns*",
                coalesce(nullif(s.holder_market_partner_id, ''), s.holder_name) as "Marktpartner ID für Nutzungsüberlassung",
                s.performing_ru as "PerformingRU",
                {status_sql} as "Exportstatus",
                {hint_sql} as "Hinweis"
            from core_usage_assignment_segments s
            where {_holding_holder_filter_sql('s')}
              and exists (
                select 1
                from core_usage_assignment_segment_movements m
                where m.usage_segment_id = s.usage_segment_id
                  and m.actual_departure_ts >= ?
                  and m.actual_departure_ts < ?
            )
            order by s.loco_no, s.segment_start_utc
            """,
            [window_start, window_end_exclusive],
        ).fetchall()

        return pd.DataFrame(rows, columns=PREVIEW_COLUMNS)

    finally:
        con.close()


def preview_to_xlsx_bytes(preview_df: pd.DataFrame) -> bytes:
    """Embedded-Vorschau zusätzlich als prüfbare XLSX-Datei bereitstellen."""
    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        preview_df.to_excel(
            writer,
            index=False,
            sheet_name="Z01 Vorschau",
        )

    return output.getvalue()
