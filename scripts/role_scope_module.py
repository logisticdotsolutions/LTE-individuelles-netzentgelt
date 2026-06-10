"""Role-based visibility rules for the portable local Netzentgelt pilot.

The temporary pilot runs locally on each workstation. Roles therefore control
what a logged-in operator can see and export inside one installation; they do
not synchronize edits between workstations.

Fail-safe principle
-------------------
No unresolved case may disappear because a source field is missing or because
an alias has not been mapped yet. Rows without an unambiguous LTE-DE or LTE-NL
scope remain visible to both operational roles.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Mapping, Sequence

import pandas as pd


PHASE9B_ROLE_SCOPE_MARKER = "NETZENTGELT_PORTABLE_ROLE_SCOPE_PHASE9B_V1_20260610"
ADMIN_ROLE = "ADMIN"
LTE_DE_ROLE = "LTE_DE"
LTE_NL_ROLE = "LTE_NL"
OPERATIONAL_ROLES = (LTE_DE_ROLE, LTE_NL_ROLE)

PERFORMING_RU_CANDIDATES = (
    "performing_ru",
    "PerformingRU",
    "CurrentContractant",
    "CALPerformingRU",
    "PerformingRailwayUndertaking",
    "RailwayUndertaking",
    "Carrier",
    "ProductionCompany",
)

ORDER_OWNER_CANDIDATES = (
    "order_owner",
    "OrderOwner",
    "ClientOrderOwner",
    "OrderOwnerName",
    "OrderOwnerCompany",
)

ROLE_ALIASES = {
    LTE_DE_ROLE: (
        "LTE DE",
        "LTE DE - LTE Germany GmbH",
        "LTE Germany GmbH",
        "LTE Germany",
    ),
    LTE_NL_ROLE: (
        "LTE NL",
        "LTE NL - LTE Netherlands B.V.",
        "LTE Netherlands B.V.",
        "LTE Netherlands",
    ),
}

_EMPTY_VALUES = {
    "",
    "-",
    "nan",
    "none",
    "null",
    "n/a",
    "na",
    "nicht verfügbar",
    "nicht verfuegbar",
    "unbekannt",
    "unknown",
}


@dataclass(frozen=True)
class ScopeDecision:
    visible_roles: tuple[str, ...]
    scope_status: str
    matched_roles: tuple[str, ...]
    performing_ru: str
    order_owner: str

    def visible_for(self, role_code: str) -> bool:
        role = normalize_role(role_code)
        return role == ADMIN_ROLE or role in self.visible_roles


def normalize_role(value: object) -> str:
    return str(value or "").strip().upper()


def normalize_company_name(value: object) -> str:
    text = str(value or "").strip().lower()
    text = (
        text.replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("ß", "ss")
    )
    return re.sub(r"[^a-z0-9]+", "", text)


def _clean(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _has_assignment(value: object) -> bool:
    return _clean(value).lower() not in _EMPTY_VALUES


def _split_values(value: object) -> list[str]:
    cleaned = _clean(value)
    if not cleaned:
        return []
    return [part.strip() for part in re.split(r"\s*\|\s*", cleaned) if part.strip()]


def _normalized_aliases() -> dict[str, set[str]]:
    return {
        role: {normalize_company_name(alias) for alias in aliases}
        for role, aliases in ROLE_ALIASES.items()
    }


def roles_for_values(values: Iterable[object]) -> set[str]:
    aliases = _normalized_aliases()
    result: set[str] = set()
    for value in values:
        for part in _split_values(value):
            normalized = normalize_company_name(part)
            if not normalized:
                continue
            for role, role_aliases in aliases.items():
                if normalized in role_aliases:
                    result.add(role)
    return result


def decide_scope(
    *,
    performing_ru: object = "",
    order_owner: object = "",
) -> ScopeDecision:
    ru_text = _clean(performing_ru)
    owner_text = _clean(order_owner)
    matched_roles = roles_for_values([ru_text, owner_text])

    if matched_roles == {LTE_DE_ROLE, LTE_NL_ROLE}:
        status = "CROSS_SCOPE_CONFLICT"
        visible_roles = OPERATIONAL_ROLES
    elif matched_roles == {LTE_DE_ROLE}:
        status = "ASSIGNED_LTE_DE"
        visible_roles = (LTE_DE_ROLE,)
    elif matched_roles == {LTE_NL_ROLE}:
        status = "ASSIGNED_LTE_NL"
        visible_roles = (LTE_NL_ROLE,)
    else:
        # Fail-safe: missing fields, unknown aliases and non-LTE assignments remain
        # visible to both operational roles until the process owner clarifies them.
        status = "SHARED_UNASSIGNED"
        visible_roles = OPERATIONAL_ROLES

    return ScopeDecision(
        visible_roles=tuple(visible_roles),
        scope_status=status,
        matched_roles=tuple(sorted(matched_roles)),
        performing_ru=ru_text,
        order_owner=owner_text,
    )


def _column(data: pd.DataFrame, candidates: Sequence[str]) -> str | None:
    by_lower = {str(column).lower(): str(column) for column in data.columns}
    for candidate in candidates:
        actual = by_lower.get(str(candidate).lower())
        if actual:
            return actual
    return None


def add_scope_columns(data: pd.DataFrame) -> pd.DataFrame:
    """Add technical scope columns without removing any row."""
    if data is None:
        return pd.DataFrame()
    result = data.copy()
    if result.empty:
        result["_scope_status"] = pd.Series(dtype="object")
        result["_scope_visible_roles"] = pd.Series(dtype="object")
        return result

    performing_ru_col = _column(result, PERFORMING_RU_CANDIDATES)
    order_owner_col = _column(result, ORDER_OWNER_CANDIDATES)
    performing_ru_values = result[performing_ru_col] if performing_ru_col else pd.Series("", index=result.index)
    order_owner_values = result[order_owner_col] if order_owner_col else pd.Series("", index=result.index)

    decisions = [
        decide_scope(performing_ru=performing_ru, order_owner=order_owner)
        for performing_ru, order_owner in zip(performing_ru_values, order_owner_values)
    ]
    result["_scope_status"] = [decision.scope_status for decision in decisions]
    result["_scope_visible_roles"] = ["|".join(decision.visible_roles) for decision in decisions]
    return result


def filter_dataframe_for_role(data: pd.DataFrame, role_code: str) -> pd.DataFrame:
    """Return only rows visible for the logged-in role.

    ADMIN is intentionally unfiltered. Technical scope helper columns are
    removed again so legacy UI tables keep their existing layout.
    """
    if data is None:
        return pd.DataFrame()
    role = normalize_role(role_code)
    if role == ADMIN_ROLE or data.empty:
        return data.copy()
    if role not in OPERATIONAL_ROLES:
        return data.iloc[0:0].copy()

    scoped = add_scope_columns(data)
    mask = scoped["_scope_visible_roles"].fillna("").astype(str).str.split("|").apply(
        lambda roles: role in roles
    )
    return scoped.loc[mask].drop(columns=["_scope_status", "_scope_visible_roles"], errors="ignore").copy()


def filter_mapping_rows_for_role(
    rows: Iterable[Mapping[str, object]],
    role_code: str,
) -> list[dict[str, object]]:
    role = normalize_role(role_code)
    result: list[dict[str, object]] = []
    for row in rows:
        payload = dict(row)
        decision = decide_scope(
            performing_ru=payload.get("PerformingRU", payload.get("performing_ru", "")),
            order_owner=payload.get("OrderOwner", payload.get("order_owner", "")),
        )
        if role == ADMIN_ROLE or decision.visible_for(role):
            payload.setdefault("Zuständigkeit", decision.scope_status)
            result.append(payload)
    return result


def restrict_performing_ru_values_for_role(
    performing_ru_values: Iterable[str],
    role_code: str,
) -> tuple[str, ...]:
    """Prevent an operational role from exporting the opposite LTE group.

    Unknown or non-LTE values remain allowed for both roles because they are
    treated as shared unresolved scope during the temporary pilot.
    """
    values = tuple(str(value).strip() for value in performing_ru_values if str(value).strip())
    role = normalize_role(role_code)
    if role == ADMIN_ROLE:
        return values
    if role not in OPERATIONAL_ROLES:
        raise PermissionError("Für diese Rolle ist kein Export zulässig.")

    matched_roles = roles_for_values(values)
    if matched_roles and role not in matched_roles:
        raise PermissionError(
            "Die ausgewählte Exportgruppe gehört nicht zur angemeldeten Rolle. "
            f"Angemeldet: {role}."
        )
    return values


def visible_primary_export_groups(
    groups: Mapping[str, Mapping[str, object]],
    role_code: str,
) -> dict[str, dict[str, object]]:
    role = normalize_role(role_code)
    if role == ADMIN_ROLE:
        return {str(key): dict(value) for key, value in groups.items()}
    if role in OPERATIONAL_ROLES and role in groups:
        return {role: dict(groups[role])}
    return {}
