"""Runtime cache for manual override suggestions.

Streamlit reruns the script when a checkbox in the suggestion editor changes.
Without this cache the suggestion engine is rebuilt on each rerun, including
DuckDB reads and GAP policy evaluation. The cache is invalidated when the
productive DuckDB timestamp or the visible finding/timeline fingerprint changes.

This runtime is loaded early by the secure entrypoint. It also switches async
correction rebuilds to CORRECTION_REBUILD, so corrections can use the raw-layer
pipeline when available.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st


PATCH_MARKER = "NETZENTGELT_SUGGESTION_CACHE_PHASE13G_V1_20260622"
_PATCHED = False


def _file_mtime_ns(path: Path) -> int:
    try:
        return int(path.stat().st_mtime_ns)
    except OSError:
        return 0


def _clean(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _series_min_max(data: pd.DataFrame, column: str) -> tuple[str, str]:
    if data is None or data.empty or column not in data.columns:
        return "", ""
    values = data[column].dropna().astype(str)
    if values.empty:
        return "", ""
    return _clean(values.min()), _clean(values.max())


def _df_fingerprint(data: pd.DataFrame | None) -> tuple[object, ...]:
    if data is None or data.empty:
        return (0, (), "", "", "", "")

    columns = tuple(str(column) for column in data.columns)
    start_min, start_max = _series_min_max(data, "period_start_utc")
    end_min, end_max = _series_min_max(data, "period_end_utc")

    return (
        len(data),
        columns,
        start_min,
        start_max,
        end_min,
        end_max,
    )


def _cache_key(
    *,
    db_path: Path,
    findings: pd.DataFrame | None,
    timeline: pd.DataFrame | None,
) -> tuple[object, ...]:
    return (
        str(db_path),
        _file_mtime_ns(db_path),
        _df_fingerprint(findings),
        _df_fingerprint(timeline),
    )


def _copy_frame(data: pd.DataFrame) -> pd.DataFrame:
    if data is None:
        return pd.DataFrame()
    return data.copy(deep=True)


def _install_correction_rebuild_default() -> None:
    try:
        import async_rebuild_runtime_module
    except ImportError:
        return

    async_rebuild_runtime_module.DEFAULT_REBUILD_MODE = "CORRECTION_REBUILD"

    try:
        import async_rebuild_status_ui_module
    except ImportError:
        return

    async_rebuild_status_ui_module.DEFAULT_REBUILD_MODE = "CORRECTION_REBUILD"


def clear_suggestion_cache() -> None:
    st.session_state.pop("manual_override_suggestion_table_cache", None)


def install_suggestion_cache_runtime() -> None:
    """Patch manual_override_ui_module.build_suggestion_table with a session cache."""
    global _PATCHED

    _install_correction_rebuild_default()

    if _PATCHED:
        return

    import manual_override_ui_module

    original = getattr(manual_override_ui_module, "build_suggestion_table", None)
    if original is None or getattr(original, "_suggestion_cache_runtime", False):
        _PATCHED = True
        return

    def cached_build_suggestion_table(
        *,
        db_path: Path,
        findings: pd.DataFrame,
        timeline: pd.DataFrame,
    ) -> pd.DataFrame:
        key = _cache_key(
            db_path=Path(db_path),
            findings=findings,
            timeline=timeline,
        )
        cached = st.session_state.get("manual_override_suggestion_table_cache")
        if isinstance(cached, dict) and cached.get("key") == key:
            return _copy_frame(cached.get("data"))

        result = original(
            db_path=Path(db_path),
            findings=findings,
            timeline=timeline,
        )
        st.session_state["manual_override_suggestion_table_cache"] = {
            "key": key,
            "data": _copy_frame(result),
        }
        return result

    cached_build_suggestion_table._suggestion_cache_runtime = True  # type: ignore[attr-defined]
    manual_override_ui_module.build_suggestion_table = cached_build_suggestion_table
    _PATCHED = True
