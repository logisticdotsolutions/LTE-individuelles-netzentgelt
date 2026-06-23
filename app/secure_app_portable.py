from __future__ import annotations

from pathlib import Path
import runpy
import sys

BASE_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = BASE_DIR / "scripts"
SECURE_APP_PATH = BASE_DIR / "app" / "secure_app.py"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from packaged_subprocess_runtime_bridge import install_packaged_subprocess_runtime  # noqa: E402
from full_import_lock_runtime_module import install_full_import_lock_runtime  # noqa: E402

PORTABLE_ENTRYPOINT_MARKER = "NETZENTGELT_PORTABLE_KEYUSER_ENTRYPOINT_PHASE13M_V1_20260623"


def _install_packaged_test_guard() -> None:
    try:
        import streamlit as st
        import pipeline_test_ui_module
    except Exception:
        return

    original = pipeline_test_ui_module.render_pipeline_test_controller
    if getattr(original, "_netzentgelt_portable_test_guard", False):
        return

    def guarded_controller(*, base_dir: Path, script_download_blob: Path, script_run_all: Path) -> None:
        runner = Path(base_dir) / ("RUN_" + "TESTS.bat")
        if not runner.is_file():
            st.subheader("Technischer Pipeline- und Testcontroller")
            st.info(
                "Dieses Key-User-Paket ist fuer den operativen Betrieb gebaut. "
                "Die Entwickler-Testsuite ist hier bewusst nicht enthalten. "
                "Datenabruf, Neuberechnung, Fallbearbeitung und Export laufen direkt in der EXE."
            )
            st.caption(
                "Automatisierte Tests bitte im Entwickler-Repository ausfuehren, nicht im entpackten Key-User-Paket."
            )
            return
        return original(
            base_dir=base_dir,
            script_download_blob=script_download_blob,
            script_run_all=script_run_all,
        )

    guarded_controller._netzentgelt_portable_test_guard = True  # type: ignore[attr-defined]
    pipeline_test_ui_module.render_pipeline_test_controller = guarded_controller


install_packaged_subprocess_runtime(force=True)
install_full_import_lock_runtime()
_install_packaged_test_guard()

runpy.run_path(str(SECURE_APP_PATH), run_name="__main__")
