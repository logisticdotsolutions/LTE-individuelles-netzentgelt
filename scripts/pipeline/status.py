"""Status helpers for pipeline and UI rebuild messages."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def status_path(root: Path) -> Path:
    return root / "data" / "02_duckdb" / "rebuild_status.json"


def default_status() -> dict[str, object]:
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


def read_status(root: Path) -> dict[str, object]:
    path = status_path(root)
    if not path.exists():
        return default_status()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_status()
    status = default_status()
    if isinstance(payload, dict):
        status.update(payload)
    return status


def write_status(root: Path, status: dict[str, object]) -> None:
    path = status_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def mark_pipeline_success(
    root: Path,
    *,
    run_id: str,
    mode: str,
    reason: str = "pipeline_run",
) -> None:
    status = read_status(root)
    status.update(
        {
            "state": "CURRENT",
            "current_run_id": run_id,
            "finished_at_utc": _now(),
            "last_success_at_utc": _now(),
            "last_error": "",
            "last_error_at_utc": "",
            "pending_rebuild": False,
            "pending_since_utc": "",
            "pending_reason": "",
            "reason": reason,
            "mode": mode,
        }
    )
    write_status(root, status)


def mark_pipeline_error(
    root: Path,
    *,
    run_id: str,
    mode: str,
    error: BaseException | str,
    reason: str = "pipeline_run",
) -> None:
    status = read_status(root)
    status.update(
        {
            "state": "ERROR",
            "current_run_id": run_id,
            "finished_at_utc": _now(),
            "last_error_at_utc": _now(),
            "last_error": str(error),
            "reason": reason,
            "mode": mode,
        }
    )
    write_status(root, status)


def reset_status(
    root: Path,
    *,
    reason: str = "manual_status_reset",
) -> None:
    status = default_status()
    status.update(
        {
            "state": "CURRENT",
            "finished_at_utc": _now(),
            "reason": reason,
        }
    )
    write_status(root, status)
