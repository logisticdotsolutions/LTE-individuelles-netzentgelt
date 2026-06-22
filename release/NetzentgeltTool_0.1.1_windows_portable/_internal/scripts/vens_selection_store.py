from __future__ import annotations

from csv import DictReader, DictWriter
from datetime import datetime, timezone
from pathlib import Path
from shutil import copy2
import re

ROOT = Path(__file__).resolve().parents[1]
MAP_DIR = ROOT / "data" / "01_mapping"
CATALOG_PATH = MAP_DIR / "ukl_user_vens_catalog.csv"
MAPPING_PATH = MAP_DIR / "performing_ru_vens_mapping.csv"
LOG_PATH = MAP_DIR / "performing_ru_vens_mapping_change_log.csv"
BACKUP_DIR = ROOT / ".vens_mapping_backups"

MAPPING_COLUMNS = (
    "performing_ru", "user_vens", "valid_from_utc", "valid_to_utc",
    "priority", "source", "comment", "active_flag",
)
LOG_COLUMNS = (
    "changed_at_utc", "action", "performing_ru", "user_vens",
    "valid_from_utc", "valid_to_utc", "priority", "changed_by", "comment",
)
CATALOG_COLUMNS = (
    "communication_partner", "vens_type", "user_vens",
    "market_location_feed_in", "market_location_consumption",
    "source", "comment", "active_flag",
)


def _clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def _norm_company(value: object) -> str:
    text = re.sub(r"^lte\s+[a-z]{2}\s*[-:]\s*", "", _clean(value).casefold())
    return re.sub(r"[^a-z0-9]+", "", text)


def _read(path: Path, columns: tuple[str, ...]) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [
            {column: _clean(row.get(column)) for column in columns}
            for row in DictReader(handle, delimiter=";")
        ]


def load_catalog(path: Path = CATALOG_PATH) -> list[dict[str, str]]:
    return [
        row for row in _read(Path(path), CATALOG_COLUMNS)
        if row["vens_type"].upper() == "NUTZER"
        and row["active_flag"].upper() not in {"N", "NO", "FALSE", "0"}
        and row["user_vens"]
    ]


def candidates_for_performing_ru(performing_ru: object, path: Path = CATALOG_PATH) -> list[dict[str, str]]:
    needle = _norm_company(performing_ru)
    if not needle:
        return []
    result = [
        row for row in load_catalog(path)
        if _norm_company(row["communication_partner"]) in needle
        or needle in _norm_company(row["communication_partner"])
    ]
    return sorted(result, key=lambda row: row["user_vens"])


def candidate_label(row: dict[str, str]) -> str:
    return (
        f"{row['user_vens']} | Entnahme {row['market_location_consumption'] or '-'} "
        f"| Rückspeisung {row['market_location_feed_in'] or '-'}"
    )


def _write_atomic(path: Path, rows: list[dict[str, str]], columns: tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_%f")
        target = BACKUP_DIR / stamp
        target.mkdir(parents=True, exist_ok=True)
        copy2(path, target / path.name)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = DictWriter(handle, fieldnames=columns, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def _append_log(row: dict[str, str]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    exists = LOG_PATH.exists()
    with LOG_PATH.open("a", encoding="utf-8-sig", newline="") as handle:
        writer = DictWriter(handle, fieldnames=LOG_COLUMNS, delimiter=";")
        if not exists:
            writer.writeheader()
        writer.writerow({column: _clean(row.get(column)) for column in LOG_COLUMNS})


def save_mapping(*, performing_ru: str, user_vens: str, valid_from_utc: str,
                 valid_to_utc: str, priority: int, changed_by: str,
                 comment: str, mapping_path: Path = MAPPING_PATH) -> str:
    if not _clean(performing_ru) or not _clean(user_vens) or not _clean(valid_from_utc):
        raise ValueError("PerformingRU, Nutzer-vEns und gültig ab sind Pflichtfelder.")
    if not _clean(comment):
        raise ValueError("Bitte eine fachliche Begründung erfassen.")
    path = Path(mapping_path)
    rows = _read(path, MAPPING_COLUMNS)
    new_row = {
        "performing_ru": _clean(performing_ru),
        "user_vens": _clean(user_vens),
        "valid_from_utc": _clean(valid_from_utc),
        "valid_to_utc": _clean(valid_to_utc),
        "priority": str(int(priority)),
        "source": "UI Fallbearbeitung",
        "comment": _clean(comment),
        "active_flag": "Y",
    }
    if any(all(row.get(column, "") == new_row[column] for column in MAPPING_COLUMNS) for row in rows):
        return "UNCHANGED"
    rows.append(new_row)
    _write_atomic(path, rows, MAPPING_COLUMNS)
    _append_log({
        "changed_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "action": "CREATE", "performing_ru": performing_ru, "user_vens": user_vens,
        "valid_from_utc": valid_from_utc, "valid_to_utc": valid_to_utc,
        "priority": str(int(priority)), "changed_by": changed_by, "comment": comment,
    })
    return "CREATED"
