"""Idempotent logging for locally prepared XLSX exports."""

from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Iterable

from export_exception_state_module import ensure_exception_state, record_export_release
from local_auth_module import DEFAULT_DB_PATH, UserContext


PHASE9C_RELEASE_DEDUP_MARKER = "NETZENTGELT_EXPORT_RELEASE_DEDUP_PHASE9C_V1_20260610"


def record_export_release_once(
    *,
    actor: UserContext,
    export_kind: str,
    export_label: str,
    date_from: date,
    date_to: date,
    file_name: str,
    content: bytes,
    exception_ids: Iterable[str],
    run_id: str = "",
    db_path: Path | str | None = None,
) -> str:
    """Return an existing matching release id or record a new release."""
    path = ensure_exception_state(db_path or DEFAULT_DB_PATH)
    ids = tuple(sorted({str(value).strip() for value in exception_ids if str(value).strip()}))
    ids_json = json.dumps(ids, ensure_ascii=False)
    digest = hashlib.sha256(content).hexdigest()

    connection = sqlite3.connect(str(path), timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            """
            select export_release_id
            from export_release
            where export_kind = ? and export_label = ?
              and performed_by = ? and performed_role = ?
              and date_from = ? and date_to = ?
              and exception_ids_json = ? and file_name = ?
              and sha256 = ? and run_id = ?
            order by created_at_utc desc, export_release_id desc
            limit 1
            """,
            [
                str(export_kind), str(export_label), actor.username, actor.role_code,
                date_from.isoformat(), date_to.isoformat(), ids_json,
                str(file_name), digest, str(run_id or "").strip(),
            ],
        ).fetchone()
    finally:
        connection.close()

    if row:
        return str(row["export_release_id"])

    return record_export_release(
        actor=actor,
        export_kind=export_kind,
        export_label=export_label,
        date_from=date_from,
        date_to=date_to,
        file_name=file_name,
        content=content,
        exception_ids=ids,
        run_id=run_id,
        db_path=path,
    )
