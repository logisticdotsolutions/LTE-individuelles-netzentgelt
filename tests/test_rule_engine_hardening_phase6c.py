from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def run(name: str) -> None:
    path = ROOT / "tests" / name
    completed = subprocess.run([sys.executable, str(path)], cwd=str(ROOT), text=True)
    if completed.returncode != 0:
        raise RuntimeError(f"Test fehlgeschlagen: {name}")

if __name__ == "__main__":
    run("test_installer_phase6c.py")
    run("test_rule_engine_hardening_phase6c_logic.py")
    print("OK: Alle Phase-6C-Tests erfolgreich.")
