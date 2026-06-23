from __future__ import annotations

"""Runtime bridge for controlled Python script execution from the app.

In a normal developer/runtime environment, ``sys.executable`` points to
``python.exe``. In the PyInstaller package it points to ``NetzentgeltMVP.exe``.

The legacy Streamlit app starts helper scripts via::

    subprocess.run([sys.executable, "scripts/...py"], ...)

Inside the packaged EXE this would start the app launcher again instead of the
helper script. The visible symptom is a new browser tab with a fresh login
screen. This bridge intercepts that case and executes the requested Python
script in-process while preserving stdout, stderr and exit codes.

It is also used in the secure Streamlit entrypoint with ``force=True`` so that
full rebuilds started from the app always receive the same operational policy:
- rolling 30-day calculation window
- central 5-minute overlap tolerance before findings/gates are written
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
OPERATIONAL_WINDOW_DAYS = 30
CENTRAL_POLICY_MARKER = "NETZENTGELT_30D_OVERLAP_POLICY_PHASE13K_V1_20260623"


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


def _install_central_overlap_tolerance_if_needed(script_path: Path) -> None:
    """Ensure run_all.py receives the 5-minute tolerance before imports bind."""
    if script_path.name.lower() != "run_all.py":
        return

    try:
        from overlap_tolerance_runtime_module import install_overlap_tolerance_runtime

        install_overlap_tolerance_runtime()
    except Exception:
        # If the tolerance module itself fails, the real pipeline error should be
        # visible through the normal stderr handling. Do not hide the original run.
        traceback.print_exc()


def _prepare_run_all_source(script_path: Path) -> str | None:
    """Return patched run_all source for the agreed rolling 30-day window."""
    if script_path.name.lower() != "run_all.py":
        return None

    source = script_path.read_text(encoding="utf-8-sig")
    source = source.replace(
        "LOOKBACK_MONTHS = 6",
        f"LOOKBACK_DAYS = {OPERATIONAL_WINDOW_DAYS}",
    )
    source = source.replace(
        "interval '{LOOKBACK_MONTHS} months'",
        "interval '{LOOKBACK_DAYS} days'",
    )
    source = source.replace(
        "{LOOKBACK_MONTHS}-Monatsfenster",
        "{LOOKBACK_DAYS}-Tagefenster",
    )
    source = source.replace(
        "relevante Loks mit DE-Bezug im letzten {LOOKBACK_MONTHS}-Monatsfenster",
        "relevante Loks mit DE-Bezug im letzten {LOOKBACK_DAYS}-Tagefenster",
    )
    source = source.replace(
        "# - Es werden nur Loks berücksichtigt, die innerhalb des Lookback-Zeitraums\n"
        "#   mindestens einmal einen DE-Bezug haben.",
        "# - Es werden nur Loks berücksichtigt, die innerhalb des 30-Tage-Fensters\n"
        "#   mindestens einmal einen DE-Bezug haben.",
    )
    return source


def _execute_script(script_path: Path, script_args: list[str]) -> int:
    _install_central_overlap_tolerance_if_needed(script_path)
    patched_source = _prepare_run_all_source(script_path)

    if patched_source is None:
        runpy.run_path(str(script_path), run_name="__main__")
        return 0

    namespace = {
        "__name__": "__main__",
        "__file__": str(script_path),
        "__package__": None,
        "__cached__": None,
    }
    exec(compile(patched_source, str(script_path), "exec"), namespace)
    return 0


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
                _execute_script(script_path, script_args)
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


def install_packaged_subprocess_runtime(*, force: bool = False):
    """Patch subprocess.run inside the EXE or when force=True in secure app."""
    global _ORIGINAL_RUN

    if not force and not _is_packaged_runtime():
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
