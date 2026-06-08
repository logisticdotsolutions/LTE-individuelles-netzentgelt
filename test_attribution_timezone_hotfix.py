from __future__ import annotations

import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "apply_netzentgelt_attribution_timezone_hotfix.py"

HEADER = '''st.title("🚆 Bahnstrom Deutschland - Tagesprüfung")
st.caption(
    "Operative Prüfung und Exportvorbereitung für das individuelle Netzentgelt. "
    "Technische Details sind bewusst nachrangig eingeordnet."
)
'''
SIDEBAR = '''file_status_box()

timeline_path = EXPORT_DIR / "core_loco_timeline.csv"
'''
IMPORT_TIME = '''        last_import = get_last_raw_import_datetime()

        if last_import:
            st.markdown(
                f"### Letzter Import am "
                f"{last_import:%d.%m.%Y} "
                f"um {last_import:%H:%M}"
            )
'''

FIXTURE = '''from types import SimpleNamespace
class Dummy:
    sidebar = None
    def title(self, *a, **k): pass
    def caption(self, *a, **k): pass
    def markdown(self, *a, **k): pass
    def write(self, *a, **k): pass
    def expander(self, *a, **k): return self
    def __enter__(self): return self
    def __exit__(self, *a): return False
st = Dummy()
st.sidebar = st
EXPORT_DIR = SimpleNamespace()
def file_status_box(): pass
def get_last_raw_import_datetime(): return None
''' + HEADER + '''
''' + SIDEBAR + '''

def render_import():
    with Dummy():
''' + IMPORT_TIME


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    original = SCRIPT.read_text(encoding="utf-8")
    patched_script = original.replace(
        "    _validate_base(raw)\n    patched = _patched_text(text)",
        "    # isolated self-test fixture\n    patched = _patched_text(text)",
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "app").mkdir()
        local_script = root / "apply_netzentgelt_attribution_timezone_hotfix.py"
        local_script.write_text(patched_script, encoding="utf-8")
        app = root / "app" / "app.py"
        app.write_bytes(FIXTURE.replace("\n", "\r\n").encode("utf-8"))
        before = sha(app)

        def run(mode: str):
            return subprocess.run(
                [sys.executable, str(local_script), mode, "--project-root", str(root)],
                text=True,
                capture_output=True,
            )

        result = run("dry-run")
        assert result.returncode == 0, result.stderr
        assert sha(app) == before

        result = run("apply")
        assert result.returncode == 0, result.stderr
        data = app.read_bytes()
        assert b"\r\n" in data
        text = data.decode("utf-8")
        assert "Konzeption, Fachlogik &amp; Umsetzung: Christoph Orgl" in text
        assert 'with st.sidebar.expander("Über dieses Tool", expanded=False):' in text
        assert "last_import_local = last_import_utc.astimezone() if last_import_utc else None" in text
        assert 'st.caption("Anzeige in lokaler Systemzeit.")' in text

        result = run("verify")
        assert result.returncode == 0, result.stderr
        result = run("apply")
        assert result.returncode == 0, result.stderr
        result = run("rollback")
        assert result.returncode == 0, result.stderr
        assert sha(app) == before

    print("OK: Dry Run, Apply, Verify, idempotentes Apply, CRLF, lokale Zeitanzeige und Rollback erfolgreich getestet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
