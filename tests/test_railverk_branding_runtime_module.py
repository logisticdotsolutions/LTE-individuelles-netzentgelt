from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from railverk_branding_runtime_module import is_lte_brand_user  # noqa: E402


def test_lte_roles_keep_lte_branding() -> None:
    for role in ["LTE_DE", "LTE_NL", "LTE_DE_NL"]:
        user = SimpleNamespace(username="operator", display_name="Operator", role_code=role)
        assert is_lte_brand_user(user)


def test_admin_without_lte_context_gets_railverk_branding() -> None:
    user = SimpleNamespace(username="railverk.admin", display_name="Railverk Admin", role_code="ADMIN")
    assert not is_lte_brand_user(user)


def test_admin_with_lte_context_keeps_lte_branding() -> None:
    user = SimpleNamespace(username="lte.admin", display_name="LTE Admin", role_code="ADMIN")
    assert is_lte_brand_user(user)
