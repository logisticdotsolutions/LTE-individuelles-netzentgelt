from __future__ import annotations
import importlib.util
from pathlib import Path
PKG = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('installer', PKG / 'apply_rule_engine_hardening_phase6b.py')
installer = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(installer)
def main() -> int:
    return 0
