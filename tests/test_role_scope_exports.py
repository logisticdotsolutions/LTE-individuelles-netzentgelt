from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from role_scope_module import (  # noqa: E402
    ADMIN_ROLE,
    LTE_DE_ROLE,
    LTE_NL_ROLE,
    restrict_performing_ru_values_for_role,
    visible_primary_export_groups,
)


def test_opposite_lte_group_is_blocked() -> None:
    assert restrict_performing_ru_values_for_role(
        ["LTE DE - LTE Germany GmbH"],
        LTE_DE_ROLE,
    ) == ("LTE DE - LTE Germany GmbH",)

    with pytest.raises(PermissionError):
        restrict_performing_ru_values_for_role(
            ["LTE NL - LTE Netherlands B.V."],
            LTE_DE_ROLE,
        )


def test_rest_group_remains_shared() -> None:
    assert restrict_performing_ru_values_for_role(
        ["External RU"],
        LTE_NL_ROLE,
    ) == ("External RU",)


def test_primary_export_groups_are_role_specific() -> None:
    groups = {
        "LTE_DE": {"title": "LTE DE"},
        "LTE_NL": {"title": "LTE NL"},
        "LTE_AT": {"title": "LTE AT"},
    }

    assert list(visible_primary_export_groups(groups, LTE_DE_ROLE)) == ["LTE_DE"]
    assert list(visible_primary_export_groups(groups, LTE_NL_ROLE)) == ["LTE_NL"]
    assert list(visible_primary_export_groups(groups, ADMIN_ROLE)) == ["LTE_DE", "LTE_NL", "LTE_AT"]
