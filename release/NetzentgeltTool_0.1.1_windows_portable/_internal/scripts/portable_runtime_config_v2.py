"""Portable SharePoint release runtime configuration.

V2 is intentionally small and focused on the first portable distribution:
- encrypted runtime config is decrypted only at process start
- Azure values are placed into os.environ for the current process tree
- initial users are seeded only when the local auth database is still empty

Security note:
A portable package that runs without user interaction must contain everything it
needs to decrypt its own config. This protects against accidental plaintext
exposure, but it is not equivalent to central secret management. Prefer a
read-only, time-limited SAS token instead of a full Storage Account Key.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken


PORTABLE_RUNTIME_V2_MARKER = "NETZENTGELT_PORTABLE_RUNTIME_CONFIG_PHASE12A_V2_20260621"
ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
DEFAULT_CONFIG_PATH = CONFIG_DIR / "portable_runtime.enc"
DEFAULT_KEY_PATH = CONFIG_DIR / "portable_runtime.key"
CONFIG_SCHEMA_VERSION = 1
AZURE_ENV_KEYS = (
    "AZURE_STORAGE_ACCOUNT_NAME",
    "AZURE_STORAGE_ACCOUNT_KEY",
    "AZURE_STORAGE_CONTAINER_NAME",
    "AZURE_STORAGE_SAS_TOKEN",
)


class PortableRuntimeConfigError(RuntimeError):
    """Understandable error for invalid portable runtime configuration."""


def _read_key(key_path: Path | str | None = None) -> bytes:
    env_value = os.getenv("NETZENTGELT_PORTABLE_RUNTIME_KEY", "").strip()
    if env_value:
        return env_value.encode("ascii")
    path = Path(key_path or DEFAULT_KEY_PATH)
    if not path.exists():
        raise PortableRuntimeConfigError(
            "Portable Runtime-Key fehlt: config/portable_runtime.key"
        )
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise PortableRuntimeConfigError(f"Portable Runtime-Key ist leer: {path}")
    return value.encode("ascii")


def load_portable_config(
    *,
    config_path: Path | str | None = None,
    key_path: Path | str | None = None,
    required: bool = False,
) -> dict[str, Any]:
    path = Path(config_path or DEFAULT_CONFIG_PATH)
    if not path.exists():
        if required:
            raise PortableRuntimeConfigError(f"Portable Runtime-Konfiguration fehlt: {path}")
        return {}
    try:
        decrypted = Fernet(_read_key(key_path)).decrypt(path.read_bytes())
        payload = json.loads(decrypted.decode("utf-8"))
    except InvalidToken as error:
        raise PortableRuntimeConfigError(
            "portable_runtime.enc konnte mit dem vorhandenen Key nicht entschlüsselt werden."
        ) from error
    except Exception as error:
        raise PortableRuntimeConfigError(
            f"Portable Runtime-Konfiguration ist ungültig: {error}"
        ) from error

    if int(payload.get("schema_version", 0)) != CONFIG_SCHEMA_VERSION:
        raise PortableRuntimeConfigError(
            f"Nicht unterstützte Config-Version: {payload.get('schema_version')!r}"
        )
    return payload


def apply_portable_azure_environment(
    *,
    config_path: Path | str | None = None,
    key_path: Path | str | None = None,
    required: bool = False,
) -> bool:
    payload = load_portable_config(
        config_path=config_path,
        key_path=key_path,
        required=required,
    )
    if not payload:
        return False
    azure = payload.get("azure") or {}
    if not isinstance(azure, dict):
        raise PortableRuntimeConfigError("Config-Abschnitt 'azure' muss ein Objekt sein.")

    applied = False
    for env_key in AZURE_ENV_KEYS:
        value = str(azure.get(env_key, "")).strip()
        if value:
            os.environ[env_key] = value
            applied = True
    return applied


def seed_portable_users_if_required(
    *,
    config_path: Path | str | None = None,
    key_path: Path | str | None = None,
    db_path: Path | str | None = None,
) -> int:
    payload = load_portable_config(config_path=config_path, key_path=key_path)
    users = payload.get("users") if payload else []
    if not users:
        return 0
    if not isinstance(users, list):
        raise PortableRuntimeConfigError("Config-Abschnitt 'users' muss eine Liste sein.")

    from local_auth_module import LocalAuthError, bootstrap_admin, create_user, has_users

    if has_users(db_path):
        return 0

    def required(user_payload: dict[str, Any], field_name: str) -> str:
        value = str(user_payload.get(field_name, "")).strip()
        if not value:
            raise PortableRuntimeConfigError(
                f"Portable User-Seed: Pflichtfeld fehlt: {field_name}"
            )
        return value

    admin_payload = next(
        (
            item for item in users
            if str(item.get("role_code", "")).strip().upper() == "ADMIN"
        ),
        None,
    )
    if admin_payload is None:
        raise PortableRuntimeConfigError("Portable User-Seed enthält keinen ADMIN-Benutzer.")

    try:
        admin_user = bootstrap_admin(
            username=required(admin_payload, "username"),
            display_name=required(admin_payload, "display_name"),
            password=required(admin_payload, "temporary_password"),
            db_path=db_path,
        )
    except LocalAuthError as error:
        raise PortableRuntimeConfigError(str(error)) from error

    created = 1
    for user_payload in users:
        if user_payload is admin_payload:
            continue
        try:
            create_user(
                actor=admin_user,
                username=required(user_payload, "username"),
                display_name=required(user_payload, "display_name"),
                password=required(user_payload, "temporary_password"),
                role_code=required(user_payload, "role_code"),
                must_change_password=bool(user_payload.get("must_change_password", True)),
                db_path=db_path,
            )
            created += 1
        except LocalAuthError as error:
            raise PortableRuntimeConfigError(str(error)) from error
    return created
