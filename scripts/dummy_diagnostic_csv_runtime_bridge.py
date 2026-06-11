"""Expose catalogued dummy locomotives to the legacy raw-data diagnostics UI."""
from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import pandas as pd

from dummy_locomotive_module import _read_mapping_rows

PHASE10B_DUMMY_DIAGNOSTIC_RUNTIME_MARKER = "NETZENTGELT_DUMMY_DIAGNOSTIC_RUNTIME_PHASE10B_V1_20260611"


def _column(data: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
    by_lower = {str(column).lower(): str(column) for column in data.columns}
    for candidate in candidates:
        if candidate.lower() in by_lower:
            return by_lower[candidate.lower()]
    return None


def _is_locomotive_movement_source(source: object) -> bool:
    try:
        return Path(str(source)).name.lower() == "locomotivemovement.csv"
    except Exception:
        return False


def _augment_dummy_types(data: pd.DataFrame) -> pd.DataFrame:
    """Mark active catalogue numbers as dummy without mutating the source CSV."""
    if data is None or data.empty:
        return data
    loco_col = _column(data, ("LocomotiveNo", "FirstLocomotiveNo", "Alias"))
    if not loco_col:
        return data
    known = {str(row.get("loco_no") or "").strip() for row in _read_mapping_rows()}
    known.discard("")
    if not known:
        return data
    result = data.copy()
    type_col = _column(result, ("LocomotiveType",))
    if not type_col:
        type_col = "LocomotiveType"
        result[type_col] = ""
    mask = result[loco_col].fillna("").astype(str).str.strip().isin(known)
    existing = result[type_col].fillna("").astype(str).str.strip()
    result.loc[mask & existing.eq(""), type_col] = "Dummy-Katalog"
    result.loc[mask & ~existing.eq("") & ~existing.str.contains("dummy", case=False, na=False), type_col] = (
        existing[mask & ~existing.eq("") & ~existing.str.contains("dummy", case=False, na=False)] + " | Dummy-Katalog"
    )
    return result


@contextmanager
def dummy_diagnostic_csv_runtime() -> Iterator[None]:
    """Temporarily enrich LocomotiveMovement reads for the Streamlit diagnostics UI."""
    original_read_csv = pd.read_csv

    def read_csv_with_dummy_catalog(*args: Any, **kwargs: Any):
        data = original_read_csv(*args, **kwargs)
        source = args[0] if args else kwargs.get("filepath_or_buffer")
        return _augment_dummy_types(data) if _is_locomotive_movement_source(source) else data

    pd.read_csv = read_csv_with_dummy_catalog
    try:
        yield
    finally:
        pd.read_csv = original_read_csv
