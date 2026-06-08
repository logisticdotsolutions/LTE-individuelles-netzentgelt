from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence


def normalize_scalar(value: object) -> str | None:
    if value is None:
        return None
    return str(value).strip()


def canonical_row_payload(row: Mapping[str, object], ordered_columns: Sequence[str]) -> str:
    payload = [(column, normalize_scalar(row.get(column))) for column in ordered_columns]
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def source_row_hash(row: Mapping[str, object], ordered_columns: Sequence[str]) -> str:
    return hashlib.sha256(canonical_row_payload(row, ordered_columns).encode("utf-8")).hexdigest()


def stable_source_row_identity(source_file: str, row_hash: str, duplicate_ordinal: int) -> str:
    if duplicate_ordinal < 1:
        raise ValueError("duplicate_ordinal muss mindestens 1 sein.")
    payload = f"{str(source_file).strip().lower()}|{row_hash}|{duplicate_ordinal}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
