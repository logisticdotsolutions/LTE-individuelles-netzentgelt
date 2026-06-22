from __future__ import annotations

from csv import DictReader
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping
import re


ROOT = Path(__file__).resolve().parents[1]
CLASSIFICATION_PATH = ROOT / "data" / "01_mapping" / "t01_classification_mapping.csv"
LOCOMOTIVE_CHARACTERISTICS_PATH = ROOT / "data" / "01_mapping" / "t01_locomotive_characteristics.csv"

ALLOWED_ORDER_CRITERIA = {"Güterverkehr", "Fernverkehr", "Regioverkehr", "S-Bahn"}
ALLOWED_USAGE_TYPES = {"OR", "LLA", "LLN", "SE", "LH", "SG"}


class T01MappingConflict(RuntimeError):
    pass


def _clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def _norm(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", _clean(value).casefold())


def _utc(value: object):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        result = value
    else:
        try:
            result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def _priority(value: object) -> int:
    try:
        return int(_clean(value) or "100")
    except ValueError:
        return 100


def load_classification_mapping(path: Path = CLASSIFICATION_PATH):
    path = Path(path)
    if not path.exists():
        return ()
    result = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in DictReader(handle, delimiter=";"):
            if _clean(row.get("active_flag")).upper() in {"N", "FALSE", "0"}:
                continue
            field = _clean(row.get("source_field"))
            value = _clean(row.get("source_value"))
            order = _clean(row.get("bestellkriterium"))
            usage = _clean(row.get("verwendungsart"))
            if not field or not value or not order or not usage:
                continue
            result.append({
                "source_field": field,
                "source_value": value,
                "bestellkriterium": order,
                "verwendungsart": usage,
                "priority": _priority(row.get("priority")),
            })
    return tuple(result)


def resolve_classification(row: Mapping[str, object], mappings) -> tuple[str | None, str | None]:
    matches = []
    for mapping in mappings:
        field = mapping["source_field"]
        expected = mapping["source_value"]
        actual = row.get(field)
        if field == "*" and expected == "*":
            matches.append(mapping)
        elif _norm(actual) == _norm(expected):
            matches.append(mapping)
    if not matches:
        return None, None
    best = min(mapping["priority"] for mapping in matches)
    values = sorted({
        (mapping["bestellkriterium"], mapping["verwendungsart"])
        for mapping in matches
        if mapping["priority"] == best
    })
    if len(values) > 1:
        raise T01MappingConflict("Mehrere gleich priorisierte T01-Klassifikationen: " + " | ".join(f"{a}/{b}" for a, b in values))
    return values[0]


def load_locomotive_characteristics(path: Path = LOCOMOTIVE_CHARACTERISTICS_PATH):
    path = Path(path)
    if not path.exists():
        return ()
    result = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in DictReader(handle, delimiter=";"):
            if _clean(row.get("active_flag")).upper() in {"N", "FALSE", "0"}:
                continue
            loco_no = _clean(row.get("loco_no"))
            if not loco_no:
                continue
            result.append({
                "loco_no": loco_no,
                "max_speed_kmh": _clean(row.get("max_speed_kmh")) or None,
                "is_multiple_unit": _clean(row.get("is_multiple_unit")).upper() in {"Y", "YES", "TRUE", "1", "JA"},
                "valid_from": _utc(row.get("valid_from_utc")),
                "valid_to": _utc(row.get("valid_to_utc")),
                "priority": _priority(row.get("priority")),
            })
    return tuple(result)


def resolve_locomotive_characteristics(*, loco_no: object, at_utc: object, mappings):
    timestamp = _utc(at_utc)
    if not _clean(loco_no) or timestamp is None:
        return {"max_speed_kmh": None, "is_multiple_unit": False}
    matches = [
        row for row in mappings
        if _clean(row["loco_no"]) == _clean(loco_no)
        and (row["valid_from"] is None or timestamp >= row["valid_from"])
        and (row["valid_to"] is None or timestamp < row["valid_to"])
    ]
    if not matches:
        return {"max_speed_kmh": None, "is_multiple_unit": False}
    best = min(row["priority"] for row in matches)
    values = {
        (row["max_speed_kmh"], row["is_multiple_unit"])
        for row in matches
        if row["priority"] == best
    }
    if len(values) > 1:
        raise T01MappingConflict(f"Mehrere gleich priorisierte Lokmerkmale für {loco_no}.")
    max_speed, is_multiple_unit = next(iter(values))
    return {"max_speed_kmh": max_speed, "is_multiple_unit": is_multiple_unit}
