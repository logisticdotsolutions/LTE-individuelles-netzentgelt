"""Related-table role scoping derived from the locomotive timeline.

Several operational CSV exports do not carry PerformingRU or OrderOwner on each
row. For those tables the temporary pilot derives visible locomotive and
transport keys from the full timeline. This avoids exposing LTE-NL-only quality
gate rows to LTE-DE users and vice versa while preserving unresolved cases.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import pandas as pd

from role_scope_module import (
    ADMIN_ROLE,
    OPERATIONAL_ROLES,
    ORDER_OWNER_CANDIDATES,
    PERFORMING_RU_CANDIDATES,
    add_scope_columns,
    filter_dataframe_for_role,
    normalize_role,
)


PHASE9B_SCOPE_REGISTRY_MARKER = "NETZENTGELT_PORTABLE_ROLE_SCOPE_REGISTRY_PHASE9B_V2_20260610"
LOCO_CANDIDATES = (
    "loco_no",
    "LocomotiveNo",
    "locomotive_no",
    "TfzE oder tEns*",
)
TRANSPORT_CANDIDATES = (
    "transport_number",
    "TransportNumber",
    "TransportNo",
    "TransportId",
    "TransportID",
)
ROW_TYPE_CANDIDATES = ("row_type", "RowType")


@dataclass(frozen=True)
class ScopeRegistry:
    visible_loco_nos: frozenset[str]
    visible_transport_numbers: frozenset[str]
    known_loco_nos: frozenset[str]
    known_transport_numbers: frozenset[str]


def _column(data: pd.DataFrame, candidates: Sequence[str]) -> str | None:
    by_lower = {str(column).lower(): str(column) for column in data.columns}
    for candidate in candidates:
        actual = by_lower.get(str(candidate).lower())
        if actual:
            return actual
    return None


def _clean_series(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip()


def _values(data: pd.DataFrame, candidates: Sequence[str]) -> frozenset[str]:
    column = _column(data, candidates)
    if not column:
        return frozenset()
    return frozenset(value for value in _clean_series(data[column]).tolist() if value)


def has_direct_scope_columns(data: pd.DataFrame) -> bool:
    return bool(
        _column(data, PERFORMING_RU_CANDIDATES)
        or _column(data, ORDER_OWNER_CANDIDATES)
    )


def build_scope_registry(timeline: pd.DataFrame, role_code: str) -> ScopeRegistry:
    """Build visible and known locomotive / transport keys from movements.

    Movement rows are preferred because generic GAP rows often have no RU and
    would otherwise broaden every locomotive to both roles. If no movement row
    exists, the full timeline is used as a fail-safe fallback.
    """
    role = normalize_role(role_code)
    if timeline is None or timeline.empty:
        return ScopeRegistry(frozenset(), frozenset(), frozenset(), frozenset())

    source = timeline.copy()
    row_type_col = _column(source, ROW_TYPE_CANDIDATES)
    if row_type_col:
        movement_mask = _clean_series(source[row_type_col]).str.upper().eq("MOVEMENT")
        movements = source.loc[movement_mask].copy()
        if not movements.empty:
            source = movements

    visible = filter_dataframe_for_role(source, role)
    return ScopeRegistry(
        visible_loco_nos=_values(visible, LOCO_CANDIDATES),
        visible_transport_numbers=_values(visible, TRANSPORT_CANDIDATES),
        known_loco_nos=_values(source, LOCO_CANDIDATES),
        known_transport_numbers=_values(source, TRANSPORT_CANDIDATES),
    )


def _related_key_masks(
    data: pd.DataFrame,
    registry: ScopeRegistry,
) -> tuple[pd.Series, pd.Series]:
    """Return (known_related_key, visible_related_key) for each row."""
    known = pd.Series(False, index=data.index, dtype=bool)
    visible = pd.Series(False, index=data.index, dtype=bool)

    loco_col = _column(data, LOCO_CANDIDATES)
    if loco_col:
        loco_values = _clean_series(data[loco_col])
        known = known | (loco_values.ne("") & loco_values.isin(registry.known_loco_nos))
        visible = visible | (loco_values.ne("") & loco_values.isin(registry.visible_loco_nos))

    transport_col = _column(data, TRANSPORT_CANDIDATES)
    if transport_col:
        transport_values = _clean_series(data[transport_col])
        known = known | (
            transport_values.ne("")
            & transport_values.isin(registry.known_transport_numbers)
        )
        visible = visible | (
            transport_values.ne("")
            & transport_values.isin(registry.visible_transport_numbers)
        )

    return known, visible


def filter_dataframe_with_registry(
    data: pd.DataFrame,
    role_code: str,
    registry: ScopeRegistry | None,
) -> pd.DataFrame:
    """Filter a generated CSV either directly or through timeline-related keys.

    Rows without RU / OrderOwner are shared only when no related timeline key can
    narrow them down. A GAP for an LTE-NL-only locomotive therefore no longer
    leaks into the LTE-DE view, while a genuinely unassigned GAP remains visible
    to both operational roles.
    """
    if data is None:
        return pd.DataFrame()
    role = normalize_role(role_code)
    if role == ADMIN_ROLE or data.empty:
        return data.copy()
    if role not in OPERATIONAL_ROLES:
        return data.iloc[0:0].copy()

    if has_direct_scope_columns(data):
        scoped = add_scope_columns(data)
        role_visible = (
            scoped["_scope_visible_roles"]
            .fillna("")
            .astype(str)
            .str.split("|")
            .apply(lambda roles: role in roles)
        )
        if registry is not None:
            known_key, visible_key = _related_key_masks(scoped, registry)
            shared = scoped["_scope_status"].fillna("").astype(str).eq("SHARED_UNASSIGNED")
            role_visible = role_visible & (~shared | ~known_key | visible_key)
        return scoped.loc[role_visible].drop(
            columns=["_scope_status", "_scope_visible_roles"],
            errors="ignore",
        ).copy()

    if registry is None:
        # Fail-safe during startup: technical rows without a registry are kept.
        return data.copy()

    loco_col = _column(data, LOCO_CANDIDATES)
    transport_col = _column(data, TRANSPORT_CANDIDATES)
    if not loco_col and not transport_col:
        return data.copy()

    known_key, visible_key = _related_key_masks(data, registry)
    return data.loc[~known_key | visible_key].copy()
