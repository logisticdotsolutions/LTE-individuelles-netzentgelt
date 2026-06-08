from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "apply_operational_day_filter_phase5c.py"

APP = '''from manual_override_ui_module import render_manual_override_cockpit
# ------------------------------------------------------

try:
    pass
except Exception as diagnostics_error:
    st.exception(diagnostics_error)

tab_overview, tab_tasks, tab_override, tab_timeline, tab_exports, tab_no_loco, tab_findings, tab_run = st.tabs([
])

def legend_caption():
    return (
                "auf den aktuellen Datenlauf vor Anwendung der Filter."
    )
'''
UI = '''PHASE5B_UI_MARKER = "NETZENTGELT_MANUAL_OVERRIDE_PHASE5B_UI_V1_20260607"

def render_manual_override_cockpit():
    st.caption(
        "Originaldaten bleiben unverändert. Das Tool schlägt nachvollziehbare Werte vor; "
        "eine fachliche Entscheidung und bewusste Bestätigung bleiben erforderlich."
    )

def render_audit():
    st.markdown("#### Phase-5B-Grenze")
'''

def run(project: Path, mode: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(INSTALLER), mode, "--project-root", str(project)],
        text=True,
        capture_output=True,
    )


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        (project / "app").mkdir()
        (project / "scripts").mkdir()
        (project / "app/app.py").write_bytes(APP.replace("\n", "\r\n").encode("utf-8"))
        (project / "scripts/manual_override_ui_module.py").write_bytes(UI.replace("\n", "\r\n").encode("utf-8"))

        before_app = (project / "app/app.py").read_bytes()
        before_ui = (project / "scripts/manual_override_ui_module.py").read_bytes()
        dry = run(project, "dry-run")
        assert dry.returncode == 0, dry.stderr
        assert (project / "app/app.py").read_bytes() == before_app
        assert (project / "scripts/manual_override_ui_module.py").read_bytes() == before_ui

        apply = run(project, "apply")
        assert apply.returncode == 0, apply.stderr
        assert b"\r\n" in (project / "app/app.py").read_bytes()
        assert (project / "scripts/operational_day_filter_module.py").exists()

        verify = run(project, "verify")
        assert verify.returncode == 0, verify.stderr

        rollback = run(project, "rollback")
        assert rollback.returncode == 0, rollback.stderr
        assert (project / "app/app.py").read_bytes() == before_app
        assert (project / "scripts/manual_override_ui_module.py").read_bytes() == before_ui
        assert not (project / "scripts/operational_day_filter_module.py").exists()

    print("PHASE5C INSTALLERTEST erfolgreich.")


if __name__ == "__main__":
    main()
