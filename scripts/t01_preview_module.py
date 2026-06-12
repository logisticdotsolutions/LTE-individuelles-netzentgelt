from __future__ import annotations

from datetime import date
from io import BytesIO
from pathlib import Path

import duckdb
import pandas as pd

from export_module import _as_ru_tuple, _placeholders, _to_day_bounds
from t01_export_module import _columns, _number, _pick, _qident, _text, _timestamp, enrich_t01_rows
from t01_preflight_module import validate_t01_rows
from ukl_preflight_module import summarize_issues_by_row


PREVIEW_COLUMNS = (
    "TfzE oder tEns*", "virtuelle Entnahmestelle", "Abfahrt Zeitpunkt*", "Abfahrt Ort*",
    "Ankunft Zeitpunkt*", "Ankunft Ort*", "Entfernung*", "Gewicht Anhängelast*",
    "Zugnummer", "Bestellkriterium*", "Verwendungsart*", "Max. Geschwindigkeit*",
    "Verkehrstag", "PerformingRU", "TransportNumber", "Exportstatus", "Hinweis",
)


def _raw_rows_without_gate(con, *, performing_ru_values, date_from: date, date_to: date):
    ru_values = _as_ru_tuple(performing_ru_values)
    columns = _columns(con, "raw_locomotivemovement")
    placeholders = _placeholders(ru_values)
    window_start, window_end = _to_day_bounds(date_from, date_to)
    ru = _pick(columns, ["PerformingRU"])
    loco = _pick(columns, ["LocomotiveNo"])
    dep = _pick(columns, ["ActualDeparture", "LocomotiveActualDeparture"])
    arr = _pick(columns, ["ActualArrival", "LocomotiveActualArrival"])
    origin = _pick(columns, ["OriginLocationCode", "LocomotiveOriginLocationCode"])
    destination = _pick(columns, ["DestinationLocationCode", "LocomotiveDestinationLocationCode"])
    origin_iso = _pick(columns, ["OriginCountryISO", "OriginCountry"])
    destination_iso = _pick(columns, ["DestinationCountryISO", "DestinationCountry"])
    country = _pick(columns, ["Country"])
    distance = _pick(columns, ["CalculatedDistance", "Distance", "RealKm", "Km"])
    gross = _pick(columns, ["TrainWeightGross"])
    traction_weight = _pick(columns, ["TractionLocomotiveWeight"])
    train_no = _pick(columns, ["TrainNo", "OriginTrainNo", "DestinationTrainNo"])
    transport_no = _pick(columns, ["TransportNumber", "TransportNumberRu"])
    movement_type = _pick(columns, ["MovementType"])
    transport_type = _pick(columns, ["TransportType"])
    traction_type = _pick(columns, ["TractionType"])
    train_type = _pick(columns, ["TrainTypeEN"])
    if not ru or not loco or not dep:
        raise RuntimeError("T01-Vorschau nicht möglich: PerformingRU, LocomotiveNo oder ActualDeparture fehlen.")
    de_filters = [f"upper(coalesce({_text(column)}, '')) = 'DE'" for column in (origin_iso, destination_iso, country) if column]
    de_filter = " or ".join(de_filters) if de_filters else "false"
    rows = con.execute(
        f"""
        select {_text(loco)}, {_text(ru)}, {_timestamp(dep)}, {_text(origin)},
               {_timestamp(arr)}, {_text(destination)}, {_number(distance)},
               ({_number(gross)} - {_number(traction_weight)}), {_text(train_no)},
               {_text(transport_no)}, {_text(movement_type)}, {_text(transport_type)},
               {_text(traction_type)}, {_text(train_type)}
        from raw_locomotivemovement
        where {_text(ru)} in ({placeholders})
          and {_timestamp(dep)} >= ? and {_timestamp(dep)} < ?
          and ({de_filter})
        order by 1, 3
        """,
        [*ru_values, window_start, window_end],
    ).fetchall()
    keys = (
        "locomotive_no", "performing_ru", "departure_ts", "departure_location",
        "arrival_ts", "arrival_location", "distance_km", "trailer_weight_t",
        "train_no", "transport_number", "movement_type", "transport_type",
        "traction_type", "train_type_en",
    )
    return [dict(zip(keys, row)) for row in rows]


def list_t01_performing_rus(*, db_path: Path, date_from: date, date_to: date) -> list[str]:
    db_path = Path(db_path)
    if not db_path.exists():
        return []
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        columns = _columns(con, "raw_locomotivemovement")
        ru = _pick(columns, ["PerformingRU"])
        dep = _pick(columns, ["ActualDeparture", "LocomotiveActualDeparture"])
        if not ru or not dep:
            return []
        window_start, window_end = _to_day_bounds(date_from, date_to)
        return [row[0] for row in con.execute(
            f"select distinct {_text(ru)} from raw_locomotivemovement where {_text(ru)} is not null and {_timestamp(dep)} >= ? and {_timestamp(dep)} < ? order by 1",
            [window_start, window_end],
        ).fetchall()]
    finally:
        con.close()


def build_t01_preview(*, db_path: Path, date_from: date, date_to: date) -> pd.DataFrame:
    ru_values = list_t01_performing_rus(db_path=Path(db_path), date_from=date_from, date_to=date_to)
    if not ru_values:
        return pd.DataFrame(columns=PREVIEW_COLUMNS)
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = enrich_t01_rows(_raw_rows_without_gate(con, performing_ru_values=tuple(ru_values), date_from=date_from, date_to=date_to))
    finally:
        con.close()
    reasons = summarize_issues_by_row(validate_t01_rows(rows))
    result = []
    for index, row in enumerate(rows, start=1):
        hint = reasons.get(index, "")
        result.append({
            "TfzE oder tEns*": row.get("locomotive_no"),
            "virtuelle Entnahmestelle": row.get("user_vens"),
            "Abfahrt Zeitpunkt*": row.get("departure_ts"),
            "Abfahrt Ort*": row.get("departure_location"),
            "Ankunft Zeitpunkt*": row.get("arrival_ts"),
            "Ankunft Ort*": row.get("arrival_location"),
            "Entfernung*": row.get("distance_km"),
            "Gewicht Anhängelast*": row.get("trailer_weight_t"),
            "Zugnummer": row.get("train_no"),
            "Bestellkriterium*": row.get("order_criterion"),
            "Verwendungsart*": row.get("usage_type"),
            "Max. Geschwindigkeit*": row.get("max_speed_kmh"),
            "Verkehrstag": row.get("traffic_day"),
            "PerformingRU": row.get("performing_ru"),
            "TransportNumber": row.get("transport_number"),
            "Exportstatus": "BLOCKIERT" if hint else "EXPORTFÄHIG",
            "Hinweis": hint,
        })
    return pd.DataFrame(result, columns=PREVIEW_COLUMNS)


def preview_to_xlsx_bytes(preview_df: pd.DataFrame) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        preview_df.to_excel(writer, index=False, sheet_name="T01 Vorschau")
    return output.getvalue()
