"""Portable Runtime-Konfiguration fuer EXE-/Key-User-Betrieb.

Prioritaet:
1. config/portable_runtime.private.json
2. portable_runtime.private.json
3. config/portable_runtime.template.json
4. portable_runtime.template.json

Private Dateien werden nicht ins Repository committed, koennen aber lokal fuer den
Release-Build verwendet werden. Templates dienen nur als Struktur und Fallback.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONFIG_CANDIDATES = (
    ROOT / "config" / "portable_runtime.private.json",
    ROOT / "portable_runtime.private.json",
    ROOT / "config" / "portable_runtime.template.json",
    ROOT / "portable_runtime.template.json",
)
AZURE_KEYS = (
    "AZURE_STORAGE_ACCOUNT_NAME",
    "AZURE_STORAGE_CONTAINER_NAME",
    "AZURE_STORAGE_ACCOUNT_KEY",
    "AZURE_STORAGE_SAS_TOKEN",
)


def _is_placeholder(value: object) -> bool:
    text = str(value or "").strip()
    return not text or text.upper().startswith("REPLACE_WITH")


def find_portable_runtime_config() -> Path | None:
    for candidate in CONFIG_CANDIDATES:
        if candidate.is_file():
            return candidate
    return None


def load_portable_runtime_config(path: Path | str | None = None) -> dict[str, Any]:
    config_path = Path(path) if path else find_portable_runtime_config()
    if config_path is None or not config_path.is_file():
        return {}
    payload = json.loads(config_path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"Portable Runtime Config ist kein JSON-Objekt: {config_path}")
    return payload


def load_azure_env_from_portable_runtime(path: Path | str | None = None) -> Path | None:
    """Setzt Azure-Umgebungsvariablen aus der Runtime Config, falls vorhanden."""
    config_path = Path(path) if path else find_portable_runtime_config()
    if config_path is None or not config_path.is_file():
        return None

    payload = load_portable_runtime_config(config_path)
    azure = payload.get("azure")
    if not isinstance(azure, dict):
        return config_path

    for key in AZURE_KEYS:
        value = azure.get(key)
        if not _is_placeholder(value):
            os.environ[str(key)] = str(value).strip()

    return config_path
