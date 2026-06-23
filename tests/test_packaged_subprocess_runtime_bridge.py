from __future__ import annotations

import subprocess
import sys

from packaged_subprocess_runtime_bridge import (
    install_packaged_subprocess_runtime,
    restore_packaged_subprocess_runtime,
)


def test_packaged_subprocess_bridge_runs_python_script_in_process(
    monkeypatch,
    tmp_path,
):
    script = tmp_path / "helper_script.py"
    marker = tmp_path / "marker.txt"
    script.write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "Path(sys.argv[1]).write_text('ok', encoding='utf-8')\n"
        "print('helper-started')\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(sys, "frozen", True, raising=False)

    original = install_packaged_subprocess_runtime()
    try:
        result = subprocess.run(
            [sys.executable, str(script), str(marker)],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
    finally:
        restore_packaged_subprocess_runtime(original)

    assert result.returncode == 0
    assert "helper-started" in result.stdout
    assert result.stderr == ""
    assert marker.read_text(encoding="utf-8") == "ok"


def test_packaged_subprocess_bridge_preserves_script_exit_code(
    monkeypatch,
    tmp_path,
):
    script = tmp_path / "failing_script.py"
    script.write_text(
        "import sys\n"
        "print('before-exit')\n"
        "raise SystemExit(7)\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(sys, "frozen", True, raising=False)

    original = install_packaged_subprocess_runtime()
    try:
        result = subprocess.run(
            [sys.executable, str(script)],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
    finally:
        restore_packaged_subprocess_runtime(original)

    assert result.returncode == 7
    assert "before-exit" in result.stdout
