"""Hintergrund-Neuberechnung nach lokalen Korrekturen.

Dieses Modul beschleunigt den Korrektur-Workflow:
- Korrektur speichern bleibt synchron und schnell.
- Neuberechnung startet danach im Hintergrund.
- Es laeuft maximal ein Rebuild gleichzeitig.
- Weitere Korrekturen waehrend eines laufenden Rebuilds setzen ein Dirty-Flag.
- Nach Abschluss des aktuellen Laufs wird bei Dirty-Flag automatisch erneut
  gerechnet.

Seit Phase 13C wird fuer lokale Korrekturen nicht mehr der komplette
`scripts/run_all.py`-Tageslauf gestartet, sondern bevorzugt der schnelle
Pipeline-Modus `OVERRIDE_REBUILD`.
"""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from datetime import datetime, timezone
import getpass
import io
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import threading
import traceback
import uuid

import streamlit as st


ROOT = Path(__file__).resolve().parents[1]
STATUS_DIR = ROOT / "data" / "02_duckdb"
STATUS_PATH = STATUS_DIR / "rebuild_status.json"
LOCK_PATH = STATUS_DIR / "rebuild.lock"
LOG_DIR = ROOT / "_rebuild_logs"
PIPELINE_ENTRYPOINT = ROOT / "scripts" / "run_pipeline.py"
DEFAULT_REBUILD_MODE = "OVERRIDE_REBUILD"
ASYNC_REBUILD_RUNTIME_MARKER = "NETZENTGELT_ASYNC_REBUILD_RUNTIME_PHASE13C_V1_20260622"

_LOCK = threading.RLock()
_WORKER: threading.Thread | None = None
_PATCHED = False


@dataclass(frozen=True)
class RebuildRequestResult:
    status: str
    message: str
    run_id: str | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _default_status() -> dict[str, object]:
    return {
        "state": "CURRENT",
        "current_run_id": "",
        "started_at_utc": "",
        "finished_at_utc": "",
        "last_success_at_utc": "",
        "last_error_at_utc": "",
        "last_error": "",
        "last_stdout_path": "",
        "last_stderr_path": "",
        "pending_rebuild": False,
        "pending_since_utc": "",
        "pending_reason": "",
        "requested_by": "",
        "reason": "",
        "mode": "",
    }


def read_rebuild_status() -> dict[str, object]:
    if not STATUS_PATH.exists():
        return _default_status()
    try:
        payload = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _default_status()
    status = _default_status()
    if isinstance(payload, dict):
        status.update(payload)
    return status


def _write_status(status: dict[str, object]) -> None:
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    temporary = STATUS_PATH.with_name(STATUS_PATH.name + ".tmp")
    temporary.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, STATUS_PATH)


_MAX_REBUILD_LOG_RUNS = 20


def _rotate_rebuild_logs() -> None:
    """Älteste Rebuild-Logs löschen; behalte die letzten _MAX_REBUILD_LOG_RUNS Läufe."""
    try:
        log_files = sorted(LOG_DIR.glob("REBUILD_*_stdout.log"), key=lambda p: p.stat().st_mtime)
        excess = len(log_files) - _MAX_REBUILD_LOG_RUNS
        for stdout_log in log_files[:excess]:
            stderr_log = stdout_log.with_name(stdout_log.name.replace("_stdout.log", "_stderr.log"))
            stdout_log.unlink(missing_ok=True)
            stderr_log.unlink(missing_ok=True)
    except OSError:
        pass


def _write_logs(run_id: str, stdout: str, stderr: str) -> tuple[str, str]:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stdout_path = LOG_DIR / f"{run_id}_stdout.log"
    stderr_path = LOG_DIR / f"{run_id}_stderr.log"
    stdout_path.write_text(stdout or "", encoding="utf-8")
    stderr_path.write_text(stderr or "", encoding="utf-8")
    _rotate_rebuild_logs()
    return str(stdout_path), str(stderr_path)


def _worker_alive() -> bool:
    return _WORKER is not None and _WORKER.is_alive()


def request_background_rebuild(
    *,
    run_all_script: Path,
    requested_by: str | None = None,
    reason: str = "manual_override",
    mode: str = DEFAULT_REBUILD_MODE,
) -> RebuildRequestResult:
    """Startet den Rebuild im Hintergrund oder markiert einen Folgelauf.

    `run_all_script` bleibt aus Kompatibilitaetsgruenden Teil der Signatur,
    wird aber fuer lokale Korrekturen nicht mehr direkt ausgefuehrt. Stattdessen
    laeuft `scripts/run_pipeline.py --mode OVERRIDE_REBUILD`.
    """
    global _WORKER
    requested_by = requested_by or getpass.getuser()
    mode = str(mode or DEFAULT_REBUILD_MODE).strip().upper()

    with _LOCK:
        if _worker_alive():
            status = read_rebuild_status()
            status["state"] = "PENDING"
            status["pending_rebuild"] = True
            status["pending_since_utc"] = _now()
            status["pending_reason"] = reason
            status["requested_by"] = requested_by
            status["mode"] = mode
            _write_status(status)
            return RebuildRequestResult(
                status="PENDING",
                message=(
                    "Neuberechnung laeuft bereits. Die Korrektur wurde gespeichert "
                    "und wird automatisch im naechsten schnellen Prueflauf beruecksichtigt."
                ),
                run_id=str(status.get("current_run_id") or "") or None,
            )

        run_id = "REBUILD_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:8].upper()
        status = _default_status()
        status.update(
            {
                "state": "QUEUED",
                "current_run_id": run_id,
                "requested_by": requested_by,
                "reason": reason,
                "mode": mode,
            }
        )
        _write_status(status)

        _WORKER = threading.Thread(
            target=_worker_loop,
            kwargs={
                "pipeline_entrypoint": PIPELINE_ENTRYPOINT,
                "mode": mode,
                "run_id": run_id,
                "requested_by": requested_by,
                "reason": reason,
            },
            daemon=True,
            name="netzentgelt-background-rebuild",
        )
        _WORKER.start()

        return RebuildRequestResult(
            status="QUEUED",
            message=f"Schnelle Neuberechnung wurde im Hintergrund gestartet ({mode}).",
            run_id=run_id,
        )


def _worker_loop(
    *,
    pipeline_entrypoint: Path,
    mode: str,
    run_id: str,
    requested_by: str,
    reason: str,
) -> None:
    global _WORKER
    current_run_id = run_id
    try:
        while True:
            result = _run_pipeline_in_process(
                pipeline_entrypoint=pipeline_entrypoint,
                mode=mode,
                run_id=current_run_id,
                requested_by=requested_by,
                reason=reason,
            )

            with _LOCK:
                status = read_rebuild_status()
                pending = bool(status.get("pending_rebuild"))

                if result.returncode != 0:
                    status.update(
                        {
                            "state": "ERROR",
                            "finished_at_utc": _now(),
                            "last_error_at_utc": _now(),
                            "last_error": _last_lines(result.stderr),
                        }
                    )
                    _write_status(status)
                    break

                if pending:
                    current_run_id = "REBUILD_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:8].upper()
                    status.update(
                        {
                            "state": "QUEUED",
                            "current_run_id": current_run_id,
                            "started_at_utc": "",
                            "finished_at_utc": "",
                            "pending_rebuild": False,
                            "pending_since_utc": "",
                            "pending_reason": "",
                            "mode": mode,
                        }
                    )
                    _write_status(status)
                    continue

                status.update(
                    {
                        "state": "CURRENT",
                        "finished_at_utc": _now(),
                        "last_success_at_utc": _now(),
                        "last_error": "",
                        "last_error_at_utc": "",
                        "pending_rebuild": False,
                        "mode": mode,
                    }
                )
                _write_status(status)
                break
    finally:
        with _LOCK:
            try:
                LOCK_PATH.unlink()
            except OSError:
                pass
            _WORKER = None


def _run_pipeline_in_process(
    *,
    pipeline_entrypoint: Path,
    mode: str,
    run_id: str,
    requested_by: str,
    reason: str,
) -> subprocess.CompletedProcess[str]:
    with _LOCK:
        STATUS_DIR.mkdir(parents=True, exist_ok=True)
        LOCK_PATH.write_text(run_id, encoding="utf-8")
        status = read_rebuild_status()
        status.update(
            {
                "state": "RUNNING",
                "current_run_id": run_id,
                "started_at_utc": _now(),
                "finished_at_utc": "",
                "requested_by": requested_by,
                "reason": reason,
                "mode": mode,
                "last_error": "",
                "last_error_at_utc": "",
            }
        )
        _write_status(status)

    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    old_argv = sys.argv[:]
    old_cwd = Path.cwd()
    return_code = 0

    try:
        os.chdir(ROOT)
        sys.argv = [str(pipeline_entrypoint), "--mode", mode]
        with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
            try:
                from overlap_tolerance_runtime_module import install_overlap_tolerance_runtime

                install_overlap_tolerance_runtime()
                runpy.run_path(str(pipeline_entrypoint), run_name="__main__")
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
                stderr_buffer.write(traceback.format_exc())
    finally:
        sys.argv = old_argv
        os.chdir(old_cwd)

    stdout = stdout_buffer.getvalue()
    stderr = stderr_buffer.getvalue()
    stdout_path, stderr_path = _write_logs(run_id, stdout, stderr)

    with _LOCK:
        status = read_rebuild_status()
        status["last_stdout_path"] = stdout_path
        status["last_stderr_path"] = stderr_path
        _write_status(status)

    return subprocess.CompletedProcess(
        args=[sys.executable, str(pipeline_entrypoint), "--mode", mode],
        returncode=return_code,
        stdout=stdout,
        stderr=stderr,
    )


def _last_lines(text: str, limit: int = 12) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return "Unbekannter Fehler bei der Neuberechnung."
    return "\n".join(cleaned.splitlines()[-limit:])


def install_async_rebuild_runtime() -> None:
    """Patcht die Korrektur-Neuberechnung auf Hintergrundbetrieb."""
    global _PATCHED
    if _PATCHED:
        return

    import manual_override_ui_module

    original = getattr(manual_override_ui_module, "_run_pipeline", None)
    if getattr(original, "_async_rebuild", False):
        _PATCHED = True
        return

    def _run_pipeline_async(run_all_script: Path) -> subprocess.CompletedProcess[str]:
        request = request_background_rebuild(
            run_all_script=Path(run_all_script),
            requested_by=getpass.getuser(),
            reason="manual_override",
            mode=DEFAULT_REBUILD_MODE,
        )
        st.session_state["async_rebuild_last_request_status"] = request.status
        st.session_state["async_rebuild_last_request_message"] = request.message
        return subprocess.CompletedProcess(
            args=[sys.executable, str(PIPELINE_ENTRYPOINT), "--mode", DEFAULT_REBUILD_MODE],
            returncode=0,
            stdout=request.message,
            stderr="",
        )

    _run_pipeline_async._async_rebuild = True  # type: ignore[attr-defined]
    manual_override_ui_module._run_pipeline = _run_pipeline_async
    _PATCHED = True


def render_async_rebuild_status() -> None:
    """Zeigt laufende oder fehlgeschlagene Hintergrund-Neuberechnungen an."""
    status = read_rebuild_status()
    state = str(status.get("state") or "CURRENT").upper()
    mode = str(status.get("mode") or DEFAULT_REBUILD_MODE)

    if state in {"QUEUED", "RUNNING"}:
        st.warning(
            "Schnelle Neuberechnung laeuft im Hintergrund. Du kannst weiter Korrekturen speichern. "
            "Exporte gelten bis zum Abschluss als nicht final."
        )
        st.caption(
            f"Modus: {mode} · "
            f"Lauf: {status.get('current_run_id') or '-'} · "
            f"Start: {status.get('started_at_utc') or 'wartet'}"
        )
        return

    if state == "PENDING":
        st.warning(
            "Schnelle Neuberechnung laeuft bereits; weitere Korrekturen wurden vorgemerkt. "
            "Nach dem aktuellen Lauf startet automatisch ein weiterer Prueflauf."
        )
        st.caption(
            f"Modus: {mode} · "
            f"Aktueller Lauf: {status.get('current_run_id') or '-'} · "
            f"Vorgemerkt seit: {status.get('pending_since_utc') or '-'}"
        )
        return

    if state == "ERROR":
        st.error(
            "Die letzte Hintergrund-Neuberechnung ist fehlgeschlagen. "
            "Der letzte gueltige Stand bleibt bestehen. Bei geaenderten Rohdaten-Overrides bitte den vollstaendigen Neuaufbau starten."
        )
        with st.expander("Technische Details zur Neuberechnung", expanded=False):
            st.caption(f"Modus: {mode}")
            st.caption(f"Lauf: {status.get('current_run_id') or '-'}")
            st.text(status.get("last_error") or "Kein Fehlertext vorhanden.")
            if status.get("last_stdout_path"):
                st.caption(f"stdout: {status.get('last_stdout_path')}")
            if status.get("last_stderr_path"):
                st.caption(f"stderr: {status.get('last_stderr_path')}")
        return

    if status.get("last_success_at_utc"):
        st.success(
            f"Letzte Hintergrund-Neuberechnung erfolgreich: {status.get('last_success_at_utc')} "
            f"({mode})"
        )
