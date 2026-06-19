from __future__ import annotations

from pathlib import Path
import sqlite3
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from dual_role_runtime_module import (  # noqa: E402
    DUAL_ROLE,
    install_dual_operator_role_runtime,
    migrate_auth_db_for_dual_role,
)
from local_auth_module import (  # noqa: E402
    LocalAuthError,
    assign_role,
    authenticate_user,
    bootstrap_admin,
    create_user,
    ensure_app_state,
    get_installation_id,
    get_user,
    hash_password,
    list_audit_events,
    set_user_active,
    verify_password,
)


def _password(seed: str) -> str:
    return f"Aa1!{seed}SecurePilot"


def test_password_hash_is_salted_and_verifiable() -> None:
    password = _password("Hash")
    encoded_a = hash_password(password)
    encoded_b = hash_password(password)

    assert encoded_a != encoded_b
    assert verify_password(password, encoded_a)
    assert not verify_password(_password("Wrong"), encoded_a)


def test_bootstrap_login_and_audit(tmp_path: Path) -> None:
    db_path = tmp_path / "auth.sqlite"
    admin = bootstrap_admin(
        username="admin.user",
        display_name="Admin User",
        password=_password("Admin"),
        db_path=db_path,
    )

    assert admin.is_admin
    assert get_installation_id(db_path)
    assert authenticate_user(
        username="admin.user",
        password=_password("Admin"),
        db_path=db_path,
    ).success
    assert not authenticate_user(
        username="admin.user",
        password=_password("Wrong"),
        db_path=db_path,
    ).success

    event_types = [event["event_type"] for event in list_audit_events(db_path=db_path)]
    assert "BOOTSTRAP_ADMIN_CREATED" in event_types
    assert "LOGIN_SUCCESS" in event_types
    assert "LOGIN_FAILED" in event_types


def test_admin_user_management_and_last_admin_protection(tmp_path: Path) -> None:
    db_path = tmp_path / "auth.sqlite"
    admin = bootstrap_admin(
        username="admin.user",
        display_name="Admin User",
        password=_password("Admin"),
        db_path=db_path,
    )
    created = create_user(
        actor=admin,
        username="lte.nl.user",
        display_name="LTE NL User",
        password=_password("Operator"),
        role_code="LTE_NL",
        db_path=db_path,
    )
    assert created.role_code == "LTE_NL"

    assign_role(
        actor=admin,
        username="lte.nl.user",
        role_code="LTE_DE",
        db_path=db_path,
    )
    assert get_user("lte.nl.user", db_path).role_code == "LTE_DE"  # type: ignore[union-attr]

    set_user_active(
        actor=admin,
        username="lte.nl.user",
        active=False,
        db_path=db_path,
    )
    assert get_user("lte.nl.user", db_path) is None

    with pytest.raises(LocalAuthError, match="letzte aktive ADMIN"):
        assign_role(
            actor=admin,
            username="admin.user",
            role_code="LTE_DE",
            db_path=db_path,
        )


def test_dual_role_schema_migration_allows_lte_de_nl_user(tmp_path: Path) -> None:
    db_path = tmp_path / "auth.sqlite"
    admin = bootstrap_admin(
        username="admin.user",
        display_name="Admin User",
        password=_password("Admin"),
        db_path=db_path,
    )

    install_dual_operator_role_runtime()
    migrate_auth_db_for_dual_role(db_path)

    created = create_user(
        actor=admin,
        username="lte.dual.user",
        display_name="LTE DE NL User",
        password=_password("Dual"),
        role_code=DUAL_ROLE,
        db_path=db_path,
    )

    assert created.role_code == DUAL_ROLE
    assert not created.is_admin
    assert authenticate_user(
        username="lte.dual.user",
        password=_password("Dual"),
        db_path=db_path,
    ).success


def test_dual_role_migration_rebuilds_existing_auth_schema_without_losing_users(tmp_path: Path) -> None:
    db_path = tmp_path / "auth.sqlite"
    admin = bootstrap_admin(
        username="admin.user",
        display_name="Admin User",
        password=_password("Admin"),
        db_path=db_path,
    )
    create_user(
        actor=admin,
        username="lte.de.user",
        display_name="LTE DE User",
        password=_password("De"),
        role_code="LTE_DE",
        db_path=db_path,
    )

    ensure_app_state(db_path)
    migrate_auth_db_for_dual_role(db_path)

    with sqlite3.connect(db_path) as connection:
        sql = connection.execute(
            "select sql from sqlite_master where type = 'table' and name = 'app_user'"
        ).fetchone()[0]

    assert DUAL_ROLE in sql
    assert get_user("admin.user", db_path).role_code == "ADMIN"  # type: ignore[union-attr]
    assert get_user("lte.de.user", db_path).role_code == "LTE_DE"  # type: ignore[union-attr]

    install_dual_operator_role_runtime()
    assign_role(
        actor=admin,
        username="lte.de.user",
        role_code=DUAL_ROLE,
        db_path=db_path,
    )
    assert get_user("lte.de.user", db_path).role_code == DUAL_ROLE  # type: ignore[union-attr]
