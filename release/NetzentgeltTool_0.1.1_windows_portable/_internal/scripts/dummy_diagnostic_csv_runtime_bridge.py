"""Expose catalogued dummy locomotives to the legacy raw-data diagnostics UI."""
from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator

import pandas as pd

from dummy_locomotive_module import _read_mapping_rows

PHASE11A_DUMMY_DIAGNOSTIC_RUNTIME_MARKER = "NETZENTGELT_DUMMY_DIAGNOSTIC_RUNTIME_PHASE11A_V1_20260611"


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


def _known_dummy_locomotives(rows: Iterable[dict[str, object]] | None = None) -> set[str]:
    """Return the normalized active catalogue once for reuse during one UI run."""
    source = _read_mapping_rows() if rows is None else rows
    known = {str(row.get("loco_no") or "").strip() for row in source}
    known.discard("")
    return known


def _augment_dummy_types(data: pd.DataFrame, known: set[str] | None = None) -> pd.DataFrame:
    """Mark active catalogue numbers as dummy without mutating the source CSV."""
    if data is None or data.empty:
        return data
    loco_col = _column(data, ("LocomotiveNo", "FirstLocomotiveNo", "Alias"))
    if not loco_col:
        return data
    catalogue = _known_dummy_locomotives() if known is None else known
    if not catalogue:
        return data
    result = data.copy()
    type_col = _column(result, ("LocomotiveType",))
    if not type_col:
        type_col = "LocomotiveType"
        result[type_col] = ""
    mask = result[loco_col].fillna("").astype(str).str.strip().isin(catalogue)
    existing = result[type_col].fillna("").astype(str).str.strip()
    enrich_mask = mask & ~existing.eq("") & ~existing.str.contains("dummy", case=False, na=False)
    result.loc[mask & existing.eq(""), type_col] = "Dummy-Katalog"
    result.loc[enrich_mask, type_col] = existing[enrich_mask] + " | Dummy-Katalog"
    return result


@contextmanager
def dummy_diagnostic_csv_runtime() -> Iterator[None]:
    """Temporarily enrich LocomotiveMovement reads for the Streamlit diagnostics UI."""
    original_read_csv = pd.read_csv
    known = _known_dummy_locomotives()

    def read_csv_with_dummy_catalog(*args: Any, **kwargs: Any):
        data = original_read_csv(*args, **kwargs)
        source = args[0] if args else kwargs.get("filepath_or_buffer")
        return _augment_dummy_types(data, known=known) if _is_locomotive_movement_source(source) else data

    pd.read_csv = read_csv_with_dummy_catalog
    try:
        yield
    finally:
        pd.read_csv = original_read_csv
