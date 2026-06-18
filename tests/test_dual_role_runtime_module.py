from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import local_auth_module as auth  # noqa: E402
import role_scope_module as scope  # noqa: E402
from dual_role_runtime_module import DUAL_ROLE, install_dual_operator_role_runtime  # noqa: E402


def test_dual_role_is_allowed_but_not_admin() -> None:
    install_dual_operator_role_runtime()
    assert DUAL_ROLE in auth.ALLOWED_ROLES
    assert auth.validate_role(DUAL_ROLE) == DUAL_ROLE
    user = auth.UserContext(
        username="dual.user",
        display_name="Dual User",
        role_code=DUAL_ROLE,
        installation_id="test",
    )
    assert user.is_admin is False


def test_dual_role_sees_lte_de_and_lte_nl_rows() -> None:
    install_dual_operator_role_runtime()
    data = pd.DataFrame(
        [
            {"transport_number": "DE1", "performing_ru": "LTE DE - LTE Germany GmbH"},
            {"transport_number": "NL1", "performing_ru": "LTE NL - LTE Netherlands B.V."},
            {"transport_number": "XX1", "performing_ru": "UNKNOWN RU"},
        ]
    )
    visible = scope.filter_dataframe_for_role(data, DUAL_ROLE)
    assert visible["transport_number"].tolist() == ["DE1", "NL1", "XX1"]


def test_single_roles_still_see_only_own_assigned_rows_plus_shared() -> None:
    install_dual_operator_role_runtime()
    data = pd.DataFrame(
        [
            {"transport_number": "DE1", "performing_ru": "LTE DE - LTE Germany GmbH"},
            {"transport_number": "NL1", "performing_ru": "LTE NL - LTE Netherlands B.V."},
            {"transport_number": "XX1", "performing_ru": "UNKNOWN RU"},
        ]
    )
    de_visible = scope.filter_dataframe_for_role(data, scope.LTE_DE_ROLE)
    nl_visible = scope.filter_dataframe_for_role(data, scope.LTE_NL_ROLE)
    assert de_visible["transport_number"].tolist() == ["DE1", "XX1"]
    assert nl_visible["transport_number"].tolist() == ["NL1", "XX1"]


def test_dual_role_gets_both_export_groups() -> None:
    install_dual_operator_role_runtime()
    groups = {
        "LTE_DE": {"label": "Germany"},
        "LTE_NL": {"label": "Netherlands"},
        "OTHER": {"label": "Other"},
    }
    visible = scope.visible_primary_export_groups(groups, DUAL_ROLE)
    assert list(visible.keys()) == ["LTE_DE", "LTE_NL"]


def test_dual_role_may_export_de_and_nl_performing_rus() -> None:
    install_dual_operator_role_runtime()
    values = scope.restrict_performing_ru_values_for_role(
        ["LTE DE - LTE Germany GmbH", "LTE NL - LTE Netherlands B.V."],
        DUAL_ROLE,
    )
    assert values == ("LTE DE - LTE Germany GmbH", "LTE NL - LTE Netherlands B.V.")
