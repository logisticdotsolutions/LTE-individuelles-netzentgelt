from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER_PATH = ROOT / "packaging" / "streamlit_exe_launcher.py"


def load_launcher_module():
    spec = importlib.util.spec_from_file_location(
        "streamlit_exe_launcher_under_test",
        LAUNCHER_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_launcher_executes_python_script_argument_without_starting_streamlit(
    monkeypatch,
    tmp_path,
):
    launcher = load_launcher_module()

    script = tmp_path / "helper_script.py"
    marker = tmp_path / "marker.txt"
    script.write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "Path(sys.argv[1]).write_text('executed', encoding='utf-8')\n",
        encoding="utf-8",
    )

    streamlit_started = {"value": False}

    def fail_if_streamlit_starts(*args, **kwargs):
        streamlit_started["value"] = True
        raise AssertionError("Streamlit/browser path must not be reached")

    monkeypatch.setattr(launcher, "_detect_entrypoint", fail_if_streamlit_starts)
    monkeypatch.setattr(launcher, "_open_browser_later", fail_if_streamlit_starts)
    monkeypatch.setattr(sys, "argv", ["NetzentgeltMVP.exe", str(script), str(marker)])
    monkeypatch.setattr(launcher, "_project_root", lambda: tmp_path)

    exit_code = launcher.main()

    assert exit_code == 0
    assert marker.read_text(encoding="utf-8") == "executed"
    assert streamlit_started["value"] is False


def test_launcher_uses_streamlit_path_without_script_argument(
    monkeypatch,
    tmp_path,
):
    launcher = load_launcher_module()

    entrypoint = tmp_path / "app.py"
    entrypoint.write_text("import streamlit as st\nst.title('x')\n", encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["NetzentgeltMVP.exe"])
    monkeypatch.setattr(launcher, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(launcher, "_detect_entrypoint", lambda root: entrypoint)
    monkeypatch.setattr(launcher, "_find_free_port", lambda: 8765)
    monkeypatch.setattr(launcher.threading, "Thread", lambda *args, **kwargs: type("NoThread", (), {"start": lambda self: None})())

    class FakeStreamlitMain:
        @staticmethod
        def main():
            return 0

    monkeypatch.setitem(sys.modules, "streamlit.web.cli", FakeStreamlitMain)

    exit_code = launcher.main()

    assert exit_code == 0
    assert sys.argv[:3] == ["streamlit", "run", str(entrypoint)]
