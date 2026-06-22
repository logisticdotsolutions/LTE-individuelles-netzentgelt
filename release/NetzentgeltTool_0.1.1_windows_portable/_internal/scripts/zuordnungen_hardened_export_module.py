from __future__ import annotations

from datetime import date
from io import BytesIO
from pathlib import Path

import duckdb

from export_module import _prepare_template_rows, _safe_file_part, _to_day_bounds
from ukl_preflight_module import raise_if_blocking_issues, validate_z01_rows
from zuordnungen_export_module import (
    LTE_HOLDING_MARKET_PARTNER_IDS,
    LTE_HOLDING_MARKET_PARTNER_NAME,
    ZUORDNUNGEN_TEMPLATE_PATH,
    ZuordnungenExportResult,
    _assert_holding_export_gate_ready,
    _load_zuordnungen_workbook,
)


def _fetch_hardened_holding_rows(
    con,
    *,
    date_from: date,
    date_to: date,
) -> list[dict[str, object]]:
    """DE-relevante Holding-Zuordnungen ohne unzulässige Firmennamen-Fallbacks lesen."""
    window_start, window_end_exclusive = _to_day_bounds(date_from, date_to)
    _assert_holding_export_gate_ready(con, date_from, date_to)

    rows = con.execute(
        """
        select
            cast(s.loco_no as varchar) as locomotive_no,
            s.segment_start_utc,
            s.segment_end_utc,
            s.performing_ru,
            s.movement_count,
            nullif(trim(cast(s.user_vens as varchar)), '') as user_vens,
            null::varchar as holder_market_partner_id
        from core_usage_assignment_segments s
        where coalesce(s.export_blocking_movement_rows, 0) = 0
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

    return [
        {
            "locomotive_no": row[0],
            "usage_start": row[1],
            "usage_end": row[2],
            "performing_ru": row[3],
            "movement_count": row[4],
            "user_vens": row[5],
            "holder_market_partner_id": row[6],
        }
        for row in rows
    ]


def _build_hardened_workbook(
    *,
    rows: list[dict[str, object]],
    holding_market_partner_id: str,
    date_from: date,
    date_to: date,
    template_path: Path,
) -> ZuordnungenExportResult:
    """Z01-XLSX ausschließlich nach erfolgreichem lokalen UKL-Preflight erzeugen."""
    raise_if_blocking_issues(
        validate_z01_rows(rows),
        export_name="Z01-Zuordnung",
    )

    workbook = _load_zuordnungen_workbook(template_path)
    worksheet = workbook["Zuordnungsdatensatzliste"]
    _prepare_template_rows(
        worksheet,
        required_data_rows=len(rows),
        first_data_row=7,
        max_column=5,
    )

    worksheet["B3"] = holding_market_partner_id
    worksheet["B3"].number_format = "@"
    worksheet["B4"] = LTE_HOLDING_MARKET_PARTNER_NAME

    for offset, row in enumerate(rows):
        row_number = 7 + offset
        worksheet.cell(row=row_number, column=1).value = str(row["locomotive_no"])
        worksheet.cell(row=row_number, column=1).number_format = "@"
        worksheet.cell(row=row_number, column=2).value = row["usage_start"]
        worksheet.cell(row=row_number, column=2).number_format = "dd.mm.yyyy hh:mm"
        worksheet.cell(row=row_number, column=3).value = row["usage_end"]
        worksheet.cell(row=row_number, column=3).number_format = "dd.mm.yyyy hh:mm"
        worksheet.cell(row=row_number, column=4).value = str(row["user_vens"] or "")
        worksheet.cell(row=row_number, column=4).number_format = "@"
        worksheet.cell(row=row_number, column=5).value = ""
        worksheet.cell(row=row_number, column=5).number_format = "@"

    output = BytesIO()
    workbook.save(output)

    return ZuordnungenExportResult(
        content=output.getvalue(),
        file_name=(
            "Zuordnungen_"
            f"{_safe_file_part('LTE_Holding_' + holding_market_partner_id)}_"
            f"{date_from.isoformat()}_bis_{date_to.isoformat()}.xlsx"
        ),
        row_count=len(rows),
        missing_required_field_count=0,
    )


def build_hardened_zuordnungen_holding_xlsx(
    *,
    db_path: Path,
    holding_market_partner_id: str,
    date_from: date,
    date_to: date,
    template_path: Path = ZUORDNUNGEN_TEMPLATE_PATH,
) -> ZuordnungenExportResult:
    """Produktiven Z01-Holding-Download für einen der beiden LTE-Mandanten erzeugen."""
    db_path = Path(db_path)
    holding_market_partner_id = str(holding_market_partner_id).strip()

    if holding_market_partner_id not in LTE_HOLDING_MARKET_PARTNER_IDS:
        raise ValueError(
            "Unbekannte LTE-Holding-Marktpartner-ID: "
            f"{holding_market_partner_id or '-'}"
        )

    if not db_path.exists():
        raise FileNotFoundError(f"DuckDB-Datei fehlt: {db_path}")

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = _fetch_hardened_holding_rows(
            con,
            date_from=date_from,
            date_to=date_to,
        )
    finally:
        con.close()

    return _build_hardened_workbook(
        rows=rows,
        holding_market_partner_id=holding_market_partner_id,
        date_from=date_from,
        date_to=date_to,
        template_path=Path(template_path),
    )
