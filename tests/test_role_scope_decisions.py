from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from role_scope_module import LTE_DE_ROLE, LTE_NL_ROLE, decide_scope  # noqa: E402


def test_lte_de_and_lte_nl_assignments() -> None:
    de = decide_scope(performing_ru="LTE DE - LTE Germany GmbH")
    nl = decide_scope(performing_ru="LTE NL - LTE Netherlands B.V.")

    assert de.scope_status == "ASSIGNED_LTE_DE"
    assert de.visible_roles == (LTE_DE_ROLE,)
    assert nl.scope_status == "ASSIGNED_LTE_NL"
    assert nl.visible_roles == (LTE_NL_ROLE,)


def test_conflict_and_unassigned_rows_are_shared() -> None:
    conflict = decide_scope(
        performing_ru="LTE DE - LTE Germany GmbH",
        order_owner="LTE NL - LTE Netherlands B.V.",
    )
    unassigned = decide_scope(performing_ru="", order_owner="")

    assert conflict.scope_status == "CROSS_SCOPE_CONFLICT"
    assert set(conflict.visible_roles) == {LTE_DE_ROLE, LTE_NL_ROLE}
    assert unassigned.scope_status == "SHARED_UNASSIGNED"
    assert set(unassigned.visible_roles) == {LTE_DE_ROLE, LTE_NL_ROLE}
