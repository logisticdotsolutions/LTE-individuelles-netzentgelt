from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Iterable

import duckdb
from openpyxl import load_workbook

from export_module import (
    NUTZUNGSMELDUNG_TEMPLATE_PATH,
    TEMPLATE_DIR,
    _as_ru_tuple,
    _fetch_usage_segments,
    _prepare_template_rows,
    _resolve_export_header,
    _safe_file_part,
)


ZUORDNUNGEN_TEMPLATE_PATH = TEMPLATE_DIR / "Vorlage_Zuordnungen.xlsx"
ZUORDNUNGEN_HEADERS = (
    "TfzE oder tEns*",
    "Beginn der Zuordnung*",
    "Ende der Zuordnung",
    "Nutzer-vEns*",
    "Marktpartner ID für Nutzungsüberlassung",
)


@dataclass(frozen=True)
class ZuordnungenExportResult:
    """Ergebnis eines dynamisch erzeugten UKL-XLSX-Zuordnungs-Exports."""

    content: bytes
    file_name: str
    row_count: int
    missing_required_field_count: int


def _load_zuordnungen_workbook(template_path: Path):
    """
    Offizielle Zuordnungsvorlage laden und auf das definierte Schema härten.

    Solange ``Vorlage_Zuordnungen.xlsx`` noch nicht im Repository versioniert ist,
    wird die bereits vorhandene Nutzungsmeldungs-Vorlage als layoutgleiche Basis
    verwendet. Die abweichende UKL-Version und die exakten fünf Spalten werden
    danach explizit gesetzt. Dadurch bleibt der Export bereits nutzbar, ohne eine
    nicht versionierte lokale Datei vorauszusetzen.
    """
    requested_template_path = Path(template_path)
    effective_template_path = (
        requested_template_path
        if requested_template_path.exists()
        else NUTZUNGSMELDUNG_TEMPLATE_PATH
    )

    if not effective_template_path.exists():
        raise FileNotFoundError(
            "XLSX-Vorlage fehlt. Erwartet wurde entweder "
            f"{requested_template_path} oder die versionierte Fallback-Vorlage "
            f"{NUTZUNGSMELDUNG_TEMPLATE_PATH}."
        )

    workbook = load_workbook(effective_template_path)

    if "Zuordnungsdatensatzliste" not in workbook.sheetnames:
        raise RuntimeError(
            "Die XLSX-Vorlage enthält das erwartete Tabellenblatt "
            "'Zuordnungsdatensatzliste' nicht."
        )

    worksheet = workbook["Zuordnungsdatensatzliste"]

    # Nutzungsmeldung besitzt eine sechste Spalte. Für Zuordnungen sind exakt
    # fünf Spalten zulässig. Zusätzliche Vorlagenspalten werden entfernt.
    if worksheet.max_column > len(ZUORDNUNGEN_HEADERS):
        worksheet.delete_cols(
            len(ZUORDNUNGEN_HEADERS) + 1,
            worksheet.max_column - len(ZUORDNUNGEN_HEADERS),
        )

    worksheet["A1"] = "Zuordnung"
    worksheet["B2"] = "Z01"

    for column_number, header in enumerate(ZUORDNUNGEN_HEADERS, start=1):
        worksheet.cell(row=6, column=column_number).value = header

    return workbook


def build_zuordnungen_xlsx(
    db_path: Path,
    performing_ru_values: Iterable[str],
    export_label: str,
    date_from: date,
    date_to: date,
    template_path: Path = ZUORDNUNGEN_TEMPLATE_PATH,
) -> ZuordnungenExportResult:
    """UKL-XLSX-Zuordnungen je PerformingRU als Download-Bytes erzeugen."""
    db_path = Path(db_path)

    if not db_path.exists():
        raise FileNotFoundError(f"DuckDB-Datei fehlt: {db_path}")

    ru_values = _as_ru_tuple(performing_ru_values)
    con = duckdb.connect(str(db_path), read_only=True)

    try:
        rows = _fetch_usage_segments(
            con=con,
            performing_ru_values=ru_values,
            date_from=date_from,
            date_to=date_to,
        )
        header_market_partner_id, header_market_partner_name = _resolve_export_header(
            con=con,
            performing_ru_values=ru_values,
        )
    finally:
        con.close()

    workbook = _load_zuordnungen_workbook(Path(template_path))
    worksheet = workbook["Zuordnungsdatensatzliste"]
    _prepare_template_rows(
        worksheet,
        required_data_rows=len(rows),
        first_data_row=7,
        max_column=5,
    )

    worksheet["B3"] = str(header_market_partner_id) if header_market_partner_id else ""
    worksheet["B3"].number_format = "@"
    worksheet["B4"] = header_market_partner_name

    first_data_row = 7

    for offset, export_row in enumerate(rows):
        row_number = first_data_row + offset

        worksheet.cell(row=row_number, column=1).value = str(export_row["locomotive_no"])
        worksheet.cell(row=row_number, column=1).number_format = "@"

        worksheet.cell(row=row_number, column=2).value = export_row["usage_start"]
        worksheet.cell(row=row_number, column=2).number_format = "dd.mm.yyyy hh:mm"

        worksheet.cell(row=row_number, column=3).value = export_row["usage_end"]
        worksheet.cell(row=row_number, column=3).number_format = "dd.mm.yyyy hh:mm"

        worksheet.cell(row=row_number, column=4).value = (
            str(export_row["user_vens"])
            if export_row["user_vens"] is not None
            else ""
        )
        worksheet.cell(row=row_number, column=4).number_format = "@"

        worksheet.cell(row=row_number, column=5).value = (
            str(export_row["holder_market_partner_id"])
            if export_row["holder_market_partner_id"] is not None
            else ""
        )
        worksheet.cell(row=row_number, column=5).number_format = "@"

    missing_required_field_count = sum(
        1
        for row in rows
        if not row["locomotive_no"]
        or not row["usage_start"]
        or not row["user_vens"]
    )

    output = BytesIO()
    workbook.save(output)

    file_name = (
        "Zuordnungen_"
        f"{_safe_file_part(export_label)}_"
        f"{date_from.isoformat()}_bis_{date_to.isoformat()}.xlsx"
    )

    return ZuordnungenExportResult(
        content=output.getvalue(),
        file_name=file_name,
        row_count=len(rows),
        missing_required_field_count=missing_required_field_count,
    )
