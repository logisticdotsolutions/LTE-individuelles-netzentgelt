from __future__ import annotations

"""Runtime bridge for Python script execution inside the packaged EXE.

In a normal developer/runtime environment, ``sys.executable`` points to
``python.exe``. In the PyInstaller package it points to ``NetzentgeltMVP.exe``.

The legacy Streamlit app starts helper scripts via::

    subprocess.run([sys.executable, "scripts/...py"], ...)

Inside the packaged EXE this would start the app launcher again instead of the
helper script. The visible symptom is a new browser tab with a fresh login
screen. This bridge intercepts exactly that packaged-EXE case and executes the
requested Python script in-process while preserving stdout, stderr and exit
codes.
"""

from contextlib import redirect_stderr, redirect_stdout
import io
import os
from pathlib import Path
import runpy
import subprocess
import sys
import traceback
from typing import Any


PACKAGED_SUBPROCESS_RUNTIME_MARKER = (
    "NETZENTGELT_PACKAGED_SUBPROCESS_RUNTIME_PHASE13G_V1_20260623"
)


_ORIGINAL_RUN = None


def _is_packaged_runtime() -> bool:
    return bool(getattr(sys, "frozen", False))


def _as_argv(args: Any) -> list[str] | None:
    if isinstance(args, (list, tuple)):
        return [str(value) for value in args]
    return None


def _is_current_executable(value: str) -> bool:
    try:
        return Path(value).resolve() == Path(sys.executable).resolve()
    except OSError:
        return Path(value).name.lower() == Path(sys.executable).name.lower()


def _should_run_in_process(args: Any) -> tuple[bool, Path | None, list[str]]:
    argv = _as_argv(args)
    if not argv or len(argv) < 2:
        return False, None, []

    if not _is_current_executable(argv[0]):
        return False, None, []

    script_path = Path(argv[1])
    if script_path.suffix.lower() != ".py":
        return False, None, []

    if not script_path.exists():
        return False, None, []

    return True, script_path, argv[2:]


def _run_python_script_in_process(
    *,
    args: Any,
    script_path: Path,
    script_args: list[str],
    kwargs: dict[str, Any],
) -> subprocess.CompletedProcess:
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    old_argv = sys.argv[:]
    old_cwd = Path.cwd()
    return_code = 0

    cwd = kwargs.get("cwd")
    text_mode = bool(
        kwargs.get("text")
        or kwargs.get("universal_newlines")
        or kwargs.get("encoding")
    )

    try:
        if cwd:
            os.chdir(str(cwd))

        sys.argv = [str(script_path), *script_args]

        with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
            try:
                runpy.run_path(str(script_path), run_name="__main__")
            except SystemExit as exit_error:
                if isinstance(exit_error.code, int):
                    return_code = int(exit_error.code)
                elif exit_error.code in (None, ""):
                    return_code = 0
                else:
                    return_code = 1
                    stderr_buffer.write(str(exit_error.code) + "\n")
            except BaseException:
                return_code = 1
                traceback.print_exc(file=stderr_buffer)
    finally:
        sys.argv = old_argv
        os.chdir(old_cwd)

    stdout_value: str | bytes = stdout_buffer.getvalue()
    stderr_value: str | bytes = stderr_buffer.getvalue()

    if not text_mode:
        stdout_value = stdout_value.encode("utf-8")
        stderr_value = stderr_value.encode("utf-8")

    result = subprocess.CompletedProcess(
        args=args,
        returncode=return_code,
        stdout=stdout_value,
        stderr=stderr_value,
    )

    if kwargs.get("check") and return_code != 0:
        raise subprocess.CalledProcessError(
            return_code,
            args,
            output=stdout_value,
            stderr=stderr_value,
        )

    return result


def install_packaged_subprocess_runtime():
    """Patch subprocess.run only inside the packaged EXE runtime."""
    global _ORIGINAL_RUN

    if not _is_packaged_runtime():
        return None

    if getattr(subprocess.run, "_netzentgelt_packaged_bridge", False):
        return getattr(subprocess.run, "_netzentgelt_original_run", None)

    original_run = subprocess.run
    _ORIGINAL_RUN = original_run

    def run_bridge(args, *popenargs, **kwargs):
        should_handle, script_path, script_args = _should_run_in_process(args)
        if should_handle and script_path is not None:
            return _run_python_script_in_process(
                args=args,
                script_path=script_path,
                script_args=script_args,
                kwargs=dict(kwargs),
            )

        return original_run(args, *popenargs, **kwargs)

    run_bridge._netzentgelt_packaged_bridge = True  # type: ignore[attr-defined]
    run_bridge._netzentgelt_original_run = original_run  # type: ignore[attr-defined]
    subprocess.run = run_bridge
    return original_run


def restore_packaged_subprocess_runtime(original_run) -> None:
    """Restore subprocess.run after the legacy app body has finished."""
    global _ORIGINAL_RUN

    if original_run is not None:
        subprocess.run = original_run
        _ORIGINAL_RUN = None
