"""CSV scoping helper for generated Netzentgelt UI exports and raw diagnostics."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pandas as pd

from role_scope_module import filter_dataframe_for_role
from role_scope_registry_module import (
    ScopeRegistry,
    build_scope_registry,
    filter_dataframe_with_registry,
    has_direct_scope_columns,
)

ROOT = Path(__file__).resolve().parents[1]
EXPORT_DIR = (ROOT / "data" / "03_exports").resolve()
RAW_DIR = (ROOT / "data" / "00_raw").resolve()
TIMELINE_PATH = (EXPORT_DIR / "core_loco_timeline.csv").resolve()


def _csv_below(path_like: object, parent: Path) -> Path | None:
    try:
        path = Path(path_like).resolve()
        path.relative_to(parent)
    except (TypeError, ValueError, OSError):
        return None
    return path if path.suffix.lower() == ".csv" else None


def _export_csv(path_like: object) -> Path | None:
    return _csv_below(path_like, EXPORT_DIR)


def _raw_csv(path_like: object) -> Path | None:
    return _csv_below(path_like, RAW_DIR)


def build_scoped_csv_reader(
    original_reader: Callable[..., pd.DataFrame],
    role_code: str,
) -> Callable[..., pd.DataFrame]:
    cache: dict[str, ScopeRegistry | None] = {"registry": None}

    def registry() -> ScopeRegistry | None:
        if cache["registry"] is not None:
            return cache["registry"]
        if not TIMELINE_PATH.exists():
            return None
        timeline = original_reader(
            TIMELINE_PATH,
            sep=None,
            engine="python",
            encoding="utf-8-sig",
        )
        cache["registry"] = build_scope_registry(timeline, role_code)
        return cache["registry"]

    def scoped_reader(*args: Any, **kwargs: Any):
        data = original_reader(*args, **kwargs)
        if not args or not isinstance(data, pd.DataFrame):
            return data

        if _export_csv(args[0]) is not None:
            return filter_dataframe_with_registry(data, role_code, registry())

        if _raw_csv(args[0]) is not None and has_direct_scope_columns(data):
            return filter_dataframe_for_role(data, role_code)

        return data

    return scoped_reader
