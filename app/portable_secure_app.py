"""Portable SharePoint entrypoint for the Netzentgelt Streamlit app.

This wrapper runs only in the portable release. It loads encrypted runtime
configuration and seeds default local users before delegating to the existing
secure_app.py entrypoint. The existing application entrypoint remains unchanged
for normal development starts via RUN_TOOL.bat.
"""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import os
from pathlib import Path
import runpy
import subprocess
import sys
import traceback

import streamlit as st


BASE_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = BASE_DIR / "scripts"
SECURE_APP_PATH = BASE_DIR / "app" / "secure_app.py"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from portable_runtime_config_v2 import (  # noqa: E402
    PortableRuntimeConfigError,
    apply_portable_azure_environment,
    seed_portable_users_if_required,
)

PORTABLE_ENTRYPOINT_MARKER = "NETZENTGELT_PORTABLE_SHAREPOINT_ENTRYPOINT_PHASE12A_V2_20260621"


def install_portable_script_subprocess_bridge() -> None:
    """Run bundled helper scripts in-process instead of launching the exe again.

    The legacy Streamlit app executes helper scripts with:
    [sys.executable, script_path]. In a normal development environment this is
    correct because sys.executable is python.exe from the local venv. In the
    portable PyInstaller package sys.executable is NetzentgeltTool.exe, which
    would start a second Streamlit server and show the login screen again.

    This bridge is installed only in the portable entrypoint and preserves the
    CompletedProcess contract expected by app/app.py.
    """

    original_run = subprocess.run

    def portable_run(*popenargs, **kwargs):  # type: ignore[no-untyped-def]
        args = popenargs[0] if popenargs else kwargs.get("args")

        if _is_bundled_python_script_call(args):
            script_path = Path(args[1]).resolve()
            cwd_value = kwargs.get("cwd")
            cwd_path = Path(cwd_value).resolve() if cwd_value else BASE_DIR
            return _run_script_in_current_process(
                args=args,
                script_path=script_path,
                cwd_path=cwd_path,
            )

        return original_run(*popenargs, **kwargs)

    subprocess.run = portable_run


def _is_bundled_python_script_call(args) -> bool:  # type: ignore[no-untyped-def]
    if not isinstance(args, (list, tuple)) or len(args) < 2:
        return False

    executable = Path(str(args[0])).resolve()
    current_executable = Path(sys.executable).resolve()
    script_path = Path(str(args[1]))

    return (
        executable == current_executable
        and script_path.suffix.lower() == ".py"
        and script_path.exists()
        and SCRIPTS_DIR.resolve() in script_path.resolve().parents
    )


def _run_script_in_current_process(
    *,
    args,
    script_path: Path,
    cwd_path: Path,
) -> subprocess.CompletedProcess:
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    original_argv = sys.argv[:]
    original_cwd = Path.cwd()

    return_code = 0

    try:
        os.chdir(cwd_path)
        sys.argv = [str(script_path)]

        with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
            try:
                runpy.run_path(str(script_path), run_name="__main__")
            except SystemExit as exit_error:
                if isinstance(exit_error.code, int):
                    return_code = exit_error.code
                elif exit_error.code in (None, ""):
                    return_code = 0
                else:
                    return_code = 1
                    stderr_buffer.write(str(exit_error.code))
                    stderr_buffer.write("\n")
            except BaseException:
                return_code = 1
                stderr_buffer.write(traceback.format_exc())
    finally:
        sys.argv = original_argv
        os.chdir(original_cwd)

    return subprocess.CompletedProcess(
        args=args,
        returncode=return_code,
        stdout=stdout_buffer.getvalue(),
        stderr=stderr_buffer.getvalue(),
    )


try:
    apply_portable_azure_environment(required=True)
    seed_portable_users_if_required()
    install_portable_script_subprocess_bridge()
except PortableRuntimeConfigError as error:
    st.error(f"Portable Konfiguration ungültig: {error}")
    st.stop()

runpy.run_path(str(SECURE_APP_PATH), run_name="__main__")
