from __future__ import annotations

from csv import DictReader
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence
import re


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MAPPING_PATH = ROOT / "data" / "01_mapping" / "performing_ru_vens_mapping.csv"


class VEnsMappingConflict(RuntimeError):
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


def load_mapping(path: Path = DEFAULT_MAPPING_PATH) -> tuple[dict[str, object], ...]:
    path = Path(path)
    if not path.exists():
        return ()
    result = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in DictReader(handle, delimiter=";"):
            if _clean(row.get("active_flag")).upper() in {"N", "FALSE", "0"}:
                continue
            if not _clean(row.get("performing_ru")) or not _clean(row.get("user_vens")):
                continue
            try:
                priority = int(_clean(row.get("priority")) or "100")
            except ValueError:
                priority = 100
            result.append({
                "performing_ru": _clean(row.get("performing_ru")),
                "user_vens": _clean(row.get("user_vens")),
                "valid_from": _utc(row.get("valid_from_utc")),
                "valid_to": _utc(row.get("valid_to_utc")),
                "priority": priority,
            })
    return tuple(result)


def resolve_user_vens(*, performing_ru: object, at_utc: object, mapping_rows) -> str | None:
    timestamp = _utc(at_utc)
    company = _norm(performing_ru)
    if timestamp is None or not company:
        return None
    candidates = [
        row for row in mapping_rows
        if _norm(row["performing_ru"]) == company
        and (row["valid_from"] is None or timestamp >= row["valid_from"])
        and (row["valid_to"] is None or timestamp < row["valid_to"])
    ]
    if not candidates:
        return None
    best = min(row["priority"] for row in candidates)
    values = sorted({row["user_vens"] for row in candidates if row["priority"] == best})
    if len(values) > 1:
        raise VEnsMappingConflict("Mehrere gleich priorisierte vEns-Mappings: " + " | ".join(values))
    return values[0] if values else None


def apply_vens_mapping(
    rows: Iterable[Mapping[str, object]],
    *,
    timestamp_keys: Sequence[str],
    mapping_path: Path = DEFAULT_MAPPING_PATH,
) -> list[dict[str, object]]:
    mapping_rows = load_mapping(Path(mapping_path))
    result = []
    for source in rows:
        row = dict(source)
        timestamp = next((row.get(key) for key in timestamp_keys if row.get(key) not in (None, "")), None)
        row["user_vens"] = resolve_user_vens(
            performing_ru=row.get("performing_ru"),
            at_utc=timestamp,
            mapping_rows=mapping_rows,
        )
        result.append(row)
    return result
