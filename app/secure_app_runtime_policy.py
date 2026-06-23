from __future__ import annotations

"""Secure app wrapper with operational runtime policy.

This wrapper installs policy bridges before the existing secure app starts:
- full import button lock while another rebuild is active
- managed helper-script execution with the agreed 30-day calculation window
- central overlap tolerance for run_all.py invocations from the app
"""

from pathlib import Path
import runpy
import sys

BASE_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = BASE_DIR / "scripts"
SECURE_APP_PATH = BASE_DIR / "app" / "secure_app.py"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from full_import_lock_runtime_module import install_full_import_lock_runtime  # noqa: E402
from packaged_subprocess_runtime_bridge import install_packaged_subprocess_runtime  # noqa: E402


POLICY_ENTRYPOINT_MARKER = "NETZENTGELT_POLICY_ENTRYPOINT_PHASE13K_V1_20260623"


install_full_import_lock_runtime()
install_packaged_subprocess_runtime(force=True)

runpy.run_path(str(SECURE_APP_PATH), run_name="__main__")
