from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import zuordnungen_hardened_runtime_bridge as hardened_bridge  # noqa: E402


def test_hardened_runtime_imports_after_export_ui_refactor() -> None:
    assert hasattr(hardened_bridge, "install_zuordnungen_hardened_runtime")
    assert hasattr(hardened_bridge, "restore_zuordnungen_hardened_runtime")
