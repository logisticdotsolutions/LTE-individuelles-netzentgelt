from __future__ import annotations

from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SECURE_APP = ROOT / "app" / "secure_app.py"


def test_direct_python_start_is_rejected_with_clear_instruction() -> None:
    result = subprocess.run(
        [sys.executable, str(SECURE_APP)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    output = (result.stdout or "") + "\n" + (result.stderr or "")
    assert result.returncode != 0
    assert "Die Netzentgelt-Anwendung ist eine Streamlit-App" in output
    assert ".\\RUN_TOOL.bat" in output
    assert "UnboundLocalError" not in output
