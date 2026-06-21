"""Portable release configuration for the Netzentgelt MVP.

This module is used by the SharePoint/portable distribution. It loads an
encrypted runtime configuration, applies Azure Data Lake credentials only in the
current process environment and optionally seeds the local user database for a
fresh portable installation.

Important security boundary:
If a portable offline package must decrypt secrets without any user interaction,
the decryption key must travel with the package. This protects against accidental
plaintext exposure in SharePoint or Git, but it is not a replacement for proper
central secret management. Prefer a read-only, time-limited SAS token over a full
storage account key for production-like distribution.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken


PORTABLE_RUNTIME_MARKER = "NETZENTGELT_PORTABLE_RUNTIME_CONFIG_PHASE12A_V1_20260621"
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


@dataclass(frozen=True)
class PortableConfigStatus:
    config_path: Path
    key_path: Path
    loaded: bool
    azure_applied: bool
    users_seeded: int
    message: str = ""


def _read_runtime_key(key_path: Path | str | None = None) -> bytes:
    """Read the Fernet key from env or local package file."""
    env_key = os.getenv("NETZENTGELT_PORTABLE_RUNTIME_KEY", "").strip()
    if env_key:
        return env_key.encode("ascii")

    path = Path(key_path or DEFAULT_KEY_PATH)
    if not path.exists():
        raise PortableRuntimeConfigError(
            "Portable Runtime-Key fehlt. Erwartet wird config/portable_runtime.key "
            "oder die Umgebungsvariable NETZENTGELT_PORTABLE_RUNTIME_KEY."
        )
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise PortableRuntimeConfigError(f"Portable Runtime-Key ist leer: {path}")
    return value.encode("ascii")


def load_portable_runtime_config(
    *,
    config_path: Path | str | None = None,
    key_path: Path | str | None = None,
    required: bool = False,
) -> dict[str, Any]:
    """Load and decrypt the portable runtime configuration.

    Returns an empty dict when the encrypted file is missing and required=False.
    """
    path = Path(config_path or DEFAULT_CONFIG_PATH)
    if not path.exists():
        if required:
            raise PortableRuntimeConfigError(f"Portable Runtime-Konfiguration fehlt: {path}")
        return {}

    try:
        key = _read_runtime_key(key_path)
        payload = Fernet(key).decrypt(path.read_bytes())
        data = json.loads(payload.decode("utf-8"))
    except InvalidToken as error:
        raise PortableRuntimeConfigError(
            "Portable Runtime-Konfiguration konnte nicht entschlüsselt werden. "
            "Key und portable_runtime.enc passen nicht zusammen."
        ) from error
    except Exception as error:
        raise PortableRuntimeConfigError(
            f"Portable Runtime-Konfiguration ist ungültig: {error}"
        ) from error

    if int(data.get("schema_version", 0)) != CONFIG_SCHEMA_VERSION:
        raise PortableRuntimeConfigError(
            "Nicht unterstützte Portable-Config-Version: "
            f"{data.get('schema_version')!r}"
        )
    return data


def apply_portable_azure_environment(
    *,
    config_path: Path | str | None = None,
    key_path: Path | str | None = None,
    required: bool = False,
    override_existing: bool = True,
) -> bool:
    """Apply Azure credentials from the encrypted portable configuration.

    The values are written only to os.environ of the current process. No .env file
    is created and no secret is written back to disk by this function.
    """
    data = load_portable_runtime_config(
        config_path=config_path,
        key_path=key_path,
        required=required,
    )
    if not data:
        return False

    azure = data.get("azure") or {}
    if not isinstance(azure, dict):
        raise PortableRuntimeConfigError("Abschnitt 'azure' muss ein Objekt sein.")

    applied = False
    for key in AZURE_ENV_KEYS:
        value = str(azure.get(key, "")).strip()
        if not value:
            continue
        if override_existing or not os.getenv(key):
            os.environ[key] = value
            applied = True

    return applied


def seed_portable_users_if_required(
    *,
    config_path: Path | str | None = None,
    key_path: Path | str | None = None,
    db_path: Path | str | None = None,
) -> int:
    """Seed ADMIN/LTE_DE/LTE_NL users for a fresh local installation.

    The seed runs only if the local user database has no users yet. Existing
    local installations are never overwritten.
    """
    data = load_portable_runtime_config(config_path=config_path, key_path=key_path)
    if not data:
        return 0

    users = data.get("users") or []
    if not isinstance(users, list) or not users:
        return 0

    from local_auth_module import (  # imported lazily to avoid circular startup imports
        LocalAuthError,
        bootstrap_admin,
        create_user,
        has_users,
    )

    if has_users(db_path):
        return 0

    admin_payload = next(
        (
            user for user in users
            if str(user.get("role_code", "")).strip().upper() == "ADMIN"
        ),
        None,
    )
    if admin_payload is None:
        raise PortableRuntimeConfigError(
            "Portable User-Seed enthält keinen ADMIN-Benutzer."
        )

    def _required(payload: dict[str, Any], key: str) -> str:
        value = str(payload.get(key, "")).strip()
        if not value:
            raise PortableRuntimeConfigError(
                f"Portable User-Seed: Pflichtfeld fehlt: {key}"
            )
        return value

    try:
        admin_user = bootstrap_admin(
            username=_required(admin_payload, "username"),
            display_name=_required(admin_payload, "display_name"),
            password=_required(admin_payload, "temporary_password"),
            must_change_password=bool(admin_payload.get("must_change_password", True)),
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
                username=_required(user_payload, "username"),
                display_name=_required(user_payload, "display_name"),
                password=_required(user_payload, "temporary_password"),
                role_code=_required(user_payload, "role_code"),
                must_change_password=bool(user_payload.get("must_change_password", True)),
                db_path=db_path,
            )
            created += 1
        except LocalAuthError as error:
            raise PortableRuntimeConfigError(str(error)) from error

    return created
