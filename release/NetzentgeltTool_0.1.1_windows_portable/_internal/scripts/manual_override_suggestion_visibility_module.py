"""Visibility rules for system suggestions after manual acceptance."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


SUGGESTION_VISIBILITY_MARKER = "NETZENTGELT_SUGGESTION_VISIBILITY_PHASE9D_V1_20260610"


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path, sep=";", dtype=str, encoding="utf-8-sig").fillna("")
    except (pd.errors.EmptyDataError, OSError, ValueError):
        return pd.DataFrame()


def _active_override_ids(overrides: pd.DataFrame) -> set[str]:
    if overrides is None or overrides.empty or "override_id" not in overrides.columns:
        return set()
    flags = overrides.get("active_flag", pd.Series("Y", index=overrides.index)).fillna("Y").astype(str).str.strip().str.upper()
    active = overrides.loc[~flags.isin(["N", "NO", "FALSE", "0"]), "override_id"]
    return {str(value).strip() for value in active.tolist() if str(value).strip()}


def accepted_active_suggestion_ids(*, acceptance_log_path: Path, overrides: pd.DataFrame) -> set[str]:
    """Return accepted suggestions whose linked local override is still active."""
    log = _read_csv(Path(acceptance_log_path))
    if log.empty or "suggestion_id" not in log.columns or "override_id" not in log.columns:
        return set()
    active_ids = _active_override_ids(overrides)
    if not active_ids:
        return set()
    linked = log[log["override_id"].fillna("").astype(str).str.strip().isin(active_ids)]
    return {str(value).strip() for value in linked["suggestion_id"].tolist() if str(value).strip()}


def hide_accepted_active_suggestions(
    suggestions: pd.DataFrame,
    *,
    acceptance_log_path: Path,
    overrides: pd.DataFrame,
) -> pd.DataFrame:
    """Hide confirmed suggestions until their linked override is deactivated."""
    if suggestions is None or suggestions.empty or "suggestion_id" not in suggestions.columns:
        return suggestions.copy() if isinstance(suggestions, pd.DataFrame) else pd.DataFrame()
    hidden_ids = accepted_active_suggestion_ids(
        acceptance_log_path=Path(acceptance_log_path),
        overrides=overrides,
    )
    if not hidden_ids:
        return suggestions.copy()
    suggestion_ids = suggestions["suggestion_id"].fillna("").astype(str).str.strip()
    return suggestions.loc[~suggestion_ids.isin(hidden_ids)].copy()
