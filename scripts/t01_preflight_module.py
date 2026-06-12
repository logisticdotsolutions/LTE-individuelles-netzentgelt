from __future__ import annotations

from datetime import datetime
from typing import Iterable, Mapping

from t01_mapping_module import ALLOWED_ORDER_CRITERIA, ALLOWED_USAGE_TYPES
from ukl_preflight_module import PreflightIssue


def _clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def _dt(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _num(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _issue(code: str, message: str, row_number: int) -> PreflightIssue:
    return PreflightIssue(code=code, message=message, row_number=row_number)


def validate_t01_rows(rows: Iterable[Mapping[str, object]]) -> list[PreflightIssue]:
    prepared = list(rows)
    issues: list[PreflightIssue] = []
    intervals: dict[str, list[tuple[datetime, datetime, int]]] = {}

    for index, row in enumerate(prepared, start=1):
        loco = _clean(row.get("locomotive_no"))
        vens = _clean(row.get("user_vens"))
        departure = _dt(row.get("departure_ts"))
        arrival = _dt(row.get("arrival_ts"))
        departure_location = _clean(row.get("departure_location"))
        arrival_location = _clean(row.get("arrival_location"))
        distance = _num(row.get("distance_km"))
        trailer_weight = _num(row.get("trailer_weight_t"))
        order_criterion = _clean(row.get("order_criterion"))
        usage_type = _clean(row.get("usage_type"))
        max_speed = _num(row.get("max_speed_kmh"))
        is_multiple_unit = bool(row.get("is_multiple_unit"))

        required = {
            "T01_TFZE_REQUIRED": (loco, "TfzE oder tEns fehlt."),
            "T01_VENS_REQUIRED": (vens, "virtuelle Entnahmestelle fehlt."),
            "T01_DEPARTURE_REQUIRED": (departure, "Abfahrtszeitpunkt fehlt oder ist ungültig."),
            "T01_DEPARTURE_LOCATION_REQUIRED": (departure_location, "Abfahrtsort fehlt."),
            "T01_ARRIVAL_REQUIRED": (arrival, "Ankunftszeitpunkt fehlt oder ist ungültig."),
            "T01_ARRIVAL_LOCATION_REQUIRED": (arrival_location, "Ankunftsort fehlt."),
            "T01_DISTANCE_REQUIRED": (distance, "Entfernung fehlt oder ist nicht numerisch."),
            "T01_TRAILER_WEIGHT_REQUIRED": (trailer_weight, "Gewicht Anhängelast fehlt oder ist nicht numerisch."),
            "T01_ORDER_CRITERION_REQUIRED": (order_criterion, "Bestellkriterium fehlt."),
            "T01_USAGE_TYPE_REQUIRED": (usage_type, "Verwendungsart fehlt."),
        }
        for code, (value, message) in required.items():
            if value in (None, ""):
                issues.append(_issue(code, message, index))

        if departure is not None and arrival is not None:
            if departure >= arrival:
                issues.append(_issue("T01_INVALID_TIME_ORDER", "Abfahrt muss zeitlich vor Ankunft liegen.", index))
            elif loco:
                intervals.setdefault(loco, []).append((departure, arrival, index))

        if distance is not None and distance <= 0:
            issues.append(_issue("T01_DISTANCE_NOT_POSITIVE", "Entfernung muss größer als 0 sein.", index))
        if trailer_weight is not None and trailer_weight < 0:
            issues.append(_issue("T01_TRAILER_WEIGHT_NEGATIVE", "Gewicht Anhängelast darf nicht negativ sein.", index))
        if order_criterion and order_criterion not in ALLOWED_ORDER_CRITERIA:
            issues.append(_issue("T01_ORDER_CRITERION_INVALID", "Bestellkriterium ist ungültig.", index))
        if usage_type and usage_type not in ALLOWED_USAGE_TYPES:
            issues.append(_issue("T01_USAGE_TYPE_INVALID", "Verwendungsart ist ungültig.", index))

        if usage_type == "OR":
            if max_speed is not None:
                issues.append(_issue("T01_OR_SPEED_MUST_BE_EMPTY", "Bei OR darf keine maximale Geschwindigkeit angegeben werden.", index))
        elif max_speed is None:
            issues.append(_issue("T01_MAX_SPEED_REQUIRED", "Maximale Geschwindigkeit fehlt.", index))
        elif max_speed <= 0:
            issues.append(_issue("T01_MAX_SPEED_NOT_POSITIVE", "Maximale Geschwindigkeit muss größer als 0 sein.", index))

        if usage_type == "LLN" and trailer_weight not in (None, 0.0):
            issues.append(_issue("T01_LLN_TRAILER_WEIGHT_MUST_BE_ZERO", "Bei LLN darf die Anhängelast nur 0 sein.", index))
        if is_multiple_unit and order_criterion == "Güterverkehr":
            issues.append(_issue("T01_MULTIPLE_UNIT_FREIGHT_FORBIDDEN", "Triebzug darf nicht als Güterverkehr gemeldet werden.", index))
        if is_multiple_unit and trailer_weight not in (None, 0.0):
            issues.append(_issue("T01_MULTIPLE_UNIT_TRAILER_WEIGHT_MUST_BE_ZERO", "Triebzug darf nur Anhängelast 0 haben.", index))

    for loco, values in intervals.items():
        ordered = sorted(values, key=lambda item: item[0])
        for previous, current in zip(ordered, ordered[1:]):
            if current[0] < previous[1]:
                issues.append(_issue("T01_OVERLAP", f"Traktionsleistungen überschneiden sich für Lok {loco} mit Zeile {previous[2]}.", current[2]))

    return issues
