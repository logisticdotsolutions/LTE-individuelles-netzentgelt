from __future__ import annotations

from typing import Iterable, Mapping

import pandas as pd


DUAL_ROLE_RUNTIME_MARKER = "NETZENTGELT_DUAL_OPERATOR_ROLE_PHASE11S_V1_20260618"
DUAL_ROLE = "LTE_DE_NL"


def install_dual_operator_role_runtime() -> None:
    """Add a non-admin dual operator role for users working in LTE_DE and LTE_NL."""
    import local_auth_module as auth
    import role_scope_module as scope

    if getattr(auth, "_PHASE11S_DUAL_ROLE_PATCHED", False):
        return

    if DUAL_ROLE not in auth.ALLOWED_ROLES:
        auth.ALLOWED_ROLES = tuple([*auth.ALLOWED_ROLES, DUAL_ROLE])

    scope.LTE_DE_NL_ROLE = DUAL_ROLE
    scope.OPERATIONAL_ROLES = (scope.LTE_DE_ROLE, scope.LTE_NL_ROLE, DUAL_ROLE)

    def _with_dual(roles: tuple[str, ...]) -> tuple[str, ...]:
        values = list(roles)
        if scope.LTE_DE_ROLE in values or scope.LTE_NL_ROLE in values:
            if DUAL_ROLE not in values:
                values.append(DUAL_ROLE)
        return tuple(values)

    def decide_scope_with_dual(*, performing_ru: object = "", order_owner: object = ""):
        ru_text = scope._clean(performing_ru)
        owner_text = scope._clean(order_owner)
        matched_roles = scope.roles_for_values([ru_text, owner_text])

        if matched_roles == {scope.LTE_DE_ROLE, scope.LTE_NL_ROLE}:
            status = "CROSS_SCOPE_CONFLICT"
            visible_roles = scope.OPERATIONAL_ROLES
        elif matched_roles == {scope.LTE_DE_ROLE}:
            status = "ASSIGNED_LTE_DE"
            visible_roles = _with_dual((scope.LTE_DE_ROLE,))
        elif matched_roles == {scope.LTE_NL_ROLE}:
            status = "ASSIGNED_LTE_NL"
            visible_roles = _with_dual((scope.LTE_NL_ROLE,))
        else:
            status = "SHARED_UNASSIGNED"
            visible_roles = scope.OPERATIONAL_ROLES

        return scope.ScopeDecision(
            visible_roles=tuple(visible_roles),
            scope_status=status,
            matched_roles=tuple(sorted(matched_roles)),
            performing_ru=ru_text,
            order_owner=owner_text,
        )

    def filter_dataframe_for_role_with_dual(data: pd.DataFrame, role_code: str) -> pd.DataFrame:
        if data is None:
            return pd.DataFrame()
        role = scope.normalize_role(role_code)
        if role == scope.ADMIN_ROLE or data.empty:
            return data.copy()
        if role not in scope.OPERATIONAL_ROLES:
            return data.iloc[0:0].copy()
        scoped = scope.add_scope_columns(data)
        mask = scoped["_scope_visible_roles"].fillna("").astype(str).str.split("|").apply(
            lambda roles: role in roles
        )
        return scoped.loc[mask].drop(columns=["_scope_status", "_scope_visible_roles"], errors="ignore").copy()

    def filter_mapping_rows_for_role_with_dual(rows: Iterable[Mapping[str, object]], role_code: str) -> list[dict[str, object]]:
        role = scope.normalize_role(role_code)
        result: list[dict[str, object]] = []
        for row in rows:
            payload = dict(row)
            decision = scope.decide_scope(
                performing_ru=payload.get("PerformingRU", payload.get("performing_ru", "")),
                order_owner=payload.get("OrderOwner", payload.get("order_owner", "")),
            )
            if role == scope.ADMIN_ROLE or decision.visible_for(role):
                payload.setdefault("Zuständigkeit", decision.scope_status)
                result.append(payload)
        return result

    def restrict_performing_ru_values_for_role_with_dual(performing_ru_values: Iterable[str], role_code: str) -> tuple[str, ...]:
        values = tuple(str(value).strip() for value in performing_ru_values if str(value).strip())
        role = scope.normalize_role(role_code)
        if role == scope.ADMIN_ROLE:
            return values
        if role not in scope.OPERATIONAL_ROLES:
            raise PermissionError("Für diese Rolle ist kein Export zulässig.")
        matched_roles = scope.roles_for_values(values)
        if role == DUAL_ROLE:
            # Dual role may export LTE_DE and LTE_NL, plus shared/unresolved/non-LTE rows.
            return values
        if matched_roles and role not in matched_roles:
            raise PermissionError(
                "Die ausgewählte Exportgruppe gehört nicht zur angemeldeten Rolle. "
                f"Angemeldet: {role}."
            )
        return values

    def visible_primary_export_groups_with_dual(groups: Mapping[str, Mapping[str, object]], role_code: str) -> dict[str, dict[str, object]]:
        role = scope.normalize_role(role_code)
        if role == scope.ADMIN_ROLE:
            return {str(key): dict(value) for key, value in groups.items()}
        if role == DUAL_ROLE:
            result: dict[str, dict[str, object]] = {}
            for key in [scope.LTE_DE_ROLE, scope.LTE_NL_ROLE]:
                if key in groups:
                    result[key] = dict(groups[key])
            return result
        if role in (scope.LTE_DE_ROLE, scope.LTE_NL_ROLE) and role in groups:
            return {role: dict(groups[role])}
        return {}

    def visible_for_with_dual(self, role_code: str) -> bool:
        role = scope.normalize_role(role_code)
        return role == scope.ADMIN_ROLE or role in self.visible_roles

    scope.decide_scope = decide_scope_with_dual
    scope.filter_dataframe_for_role = filter_dataframe_for_role_with_dual
    scope.filter_mapping_rows_for_role = filter_mapping_rows_for_role_with_dual
    scope.restrict_performing_ru_values_for_role = restrict_performing_ru_values_for_role_with_dual
    scope.visible_primary_export_groups = visible_primary_export_groups_with_dual
    scope.ScopeDecision.visible_for = visible_for_with_dual

    auth._PHASE11S_DUAL_ROLE_PATCHED = True
    scope._PHASE11S_DUAL_ROLE_PATCHED = True
