"""Local SQLite state for documented export exceptions and release manifests."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable
import uuid

from local_auth_module import (
    DEFAULT_DB_PATH,
    LocalAuthError,
    UserContext,
    append_audit_event,
    ensure_app_state,
    get_installation_id,
    utc_now_text,
)


PHASE9C_EXCEPTION_STATE_MARKER = "NETZENTGELT_EXPORT_EXCEPTION_STATE_PHASE9C_V2_20260610"


@dataclass(frozen=True)
class ExportBlocker:
    fingerprint: str
    blocker_type: str
    rule_id: str
    loco_no: str
    performing_ru: str
    period_start_utc: str
    period_end_utc: str
    message: str
    run_id: str = ""

    def label(self) -> str:
        parts = [self.rule_id or self.blocker_type]
        if self.loco_no:
            parts.append(f"Lok {self.loco_no}")
        if self.period_start_utc or self.period_end_utc:
            parts.append(f"{self.period_start_utc or '-'} bis {self.period_end_utc or '-'}")
        return " | ".join(parts)


@dataclass(frozen=True)
class ExportReleaseStatus:
    required_blockers: tuple[ExportBlocker, ...]
    active_exception_ids: tuple[str, ...]
    missing_blockers: tuple[ExportBlocker, ...]

    @property
    def released(self) -> bool:
        return not self.missing_blockers


def stable_blocker_fingerprint(
    *,
    blocker_type: str,
    rule_id: str = "",
    loco_no: str = "",
    performing_ru: str = "",
    period_start_utc: str = "",
    period_end_utc: str = "",
    message: str = "",
    run_id: str = "",
) -> str:
    payload = {
        "blocker_type": str(blocker_type or "").strip().upper(),
        "rule_id": str(rule_id or "").strip().upper(),
        "loco_no": str(loco_no or "").strip(),
        "performing_ru": str(performing_ru or "").strip(),
        "period_start_utc": str(period_start_utc or "").strip(),
        "period_end_utc": str(period_end_utc or "").strip(),
        "message": str(message or "").strip(),
        "run_id": str(run_id or "").strip(),
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def make_blocker(
    *,
    blocker_type: str,
    rule_id: str = "",
    loco_no: str = "",
    performing_ru: str = "",
    period_start_utc: str = "",
    period_end_utc: str = "",
    message: str = "",
    run_id: str = "",
) -> ExportBlocker:
    return ExportBlocker(
        fingerprint=stable_blocker_fingerprint(
            blocker_type=blocker_type,
            rule_id=rule_id,
            loco_no=loco_no,
            performing_ru=performing_ru,
            period_start_utc=period_start_utc,
            period_end_utc=period_end_utc,
            message=message,
            run_id=run_id,
        ),
        blocker_type=str(blocker_type or "").strip().upper(),
        rule_id=str(rule_id or "").strip().upper(),
        loco_no=str(loco_no or "").strip(),
        performing_ru=str(performing_ru or "").strip(),
        period_start_utc=str(period_start_utc or "").strip(),
        period_end_utc=str(period_end_utc or "").strip(),
        message=str(message or "").strip(),
        run_id=str(run_id or "").strip(),
    )


def _connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(db_path or DEFAULT_DB_PATH).resolve()
    ensure_app_state(path)
    connection = sqlite3.connect(str(path), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("pragma foreign_keys = on")
    connection.execute("pragma busy_timeout = 5000")
    return connection


def _columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"pragma table_info({table_name})").fetchall()}


def _ensure_column(connection: sqlite3.Connection, table_name: str, column_name: str, ddl: str) -> None:
    if column_name not in _columns(connection, table_name):
        connection.execute(f"alter table {table_name} add column {column_name} {ddl}")


def ensure_exception_state(db_path: Path | str | None = None) -> Path:
    path = Path(db_path or DEFAULT_DB_PATH).resolve()
    ensure_app_state(path)
    with _connect(path) as connection:
        connection.executescript(
            """
            create table if not exists finding_exception (
                exception_id text primary key,
                finding_fingerprint text not null,
                blocker_type text not null,
                rule_id text,
                loco_no text,
                performing_ru text,
                period_start_utc text,
                period_end_utc text,
                comment text not null,
                status text not null check (status in ('ACTIVE', 'REVOKED')),
                created_by text not null,
                created_at_utc text not null,
                revoked_by text,
                revoked_at_utc text,
                revocation_comment text,
                installation_id text not null,
                run_id text not null default ''
            );

            create index if not exists idx_finding_exception_active
                on finding_exception(finding_fingerprint, status);

            create table if not exists export_release (
                export_release_id text primary key,
                export_kind text not null,
                export_label text not null,
                performed_by text not null,
                performed_role text not null,
                created_at_utc text not null,
                date_from text not null,
                date_to text not null,
                exception_count integer not null,
                exception_ids_json text not null,
                file_name text not null,
                sha256 text not null,
                installation_id text not null,
                run_id text not null default ''
            );
            """
        )
        _ensure_column(connection, "finding_exception", "run_id", "text not null default ''")
        _ensure_column(connection, "export_release", "run_id", "text not null default ''")
    return path


def _active_exception_rows(
    fingerprints: Iterable[str],
    db_path: Path | str | None = None,
) -> list[sqlite3.Row]:
    values = tuple(sorted({str(value).strip() for value in fingerprints if str(value).strip()}))
    if not values:
        return []
    ensure_exception_state(db_path)
    placeholders = ", ".join("?" for _ in values)
    with _connect(db_path) as connection:
        return connection.execute(
            f"""
            select exception_id, finding_fingerprint
            from finding_exception
            where status = 'ACTIVE'
              and finding_fingerprint in ({placeholders})
            order by created_at_utc desc, exception_id desc
            """,
            values,
        ).fetchall()


def evaluate_release_status(
    blockers: Iterable[ExportBlocker],
    db_path: Path | str | None = None,
) -> ExportReleaseStatus:
    unique = {blocker.fingerprint: blocker for blocker in blockers}
    ordered = tuple(sorted(unique.values(), key=lambda item: (item.rule_id, item.loco_no, item.period_start_utc, item.fingerprint)))
    active_rows = _active_exception_rows([item.fingerprint for item in ordered], db_path)
    active_by_fingerprint = {str(row["finding_fingerprint"]): str(row["exception_id"]) for row in active_rows}
    missing = tuple(item for item in ordered if item.fingerprint not in active_by_fingerprint)
    ids = tuple(sorted(set(active_by_fingerprint.values())))
    return ExportReleaseStatus(ordered, ids, missing)


def create_exception(
    *,
    actor: UserContext,
    blocker: ExportBlocker,
    comment: str,
    db_path: Path | str | None = None,
) -> str:
    reason = str(comment or "").strip()
    if len(reason) < 10:
        raise LocalAuthError("Bitte eine nachvollziehbare Begründung mit mindestens 10 Zeichen erfassen.")
    ensure_exception_state(db_path)
    existing = _active_exception_rows([blocker.fingerprint], db_path)
    if existing:
        return str(existing[0]["exception_id"])

    exception_id = "EXC_" + uuid.uuid4().hex.upper()
    installation_id = get_installation_id(db_path)
    with _connect(db_path) as connection:
        connection.execute(
            """
            insert into finding_exception (
                exception_id, finding_fingerprint, blocker_type, rule_id, loco_no,
                performing_ru, period_start_utc, period_end_utc, comment, status,
                created_by, created_at_utc, installation_id, run_id
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?, ?)
            """,
            [
                exception_id,
                blocker.fingerprint,
                blocker.blocker_type,
                blocker.rule_id,
                blocker.loco_no,
                blocker.performing_ru,
                blocker.period_start_utc,
                blocker.period_end_utc,
                reason,
                actor.username,
                utc_now_text(),
                installation_id,
                blocker.run_id,
            ],
        )
    append_audit_event(
        event_type="CREATE_EXPORT_EXCEPTION",
        actor_username=actor.username,
        actor_role=actor.role_code,
        object_type="FINDING_EXCEPTION",
        object_id=exception_id,
        comment=reason,
        details=asdict(blocker),
        db_path=db_path,
    )
    return exception_id


def revoke_exception(
    *,
    actor: UserContext,
    exception_id: str,
    comment: str,
    db_path: Path | str | None = None,
) -> None:
    if not actor.is_admin:
        raise LocalAuthError("Ausnahmen dürfen ausschließlich durch ADMIN widerrufen werden.")
    reason = str(comment or "").strip()
    if len(reason) < 10:
        raise LocalAuthError("Bitte eine Begründung für den Widerruf mit mindestens 10 Zeichen erfassen.")
    ensure_exception_state(db_path)
    with _connect(db_path) as connection:
        updated = connection.execute(
            """
            update finding_exception
            set status = 'REVOKED', revoked_by = ?, revoked_at_utc = ?, revocation_comment = ?
            where exception_id = ? and status = 'ACTIVE'
            """,
            [actor.username, utc_now_text(), reason, str(exception_id)],
        ).rowcount
    if not updated:
        raise LocalAuthError("Aktive Ausnahme wurde nicht gefunden.")
    append_audit_event(
        event_type="REVOKE_EXPORT_EXCEPTION",
        actor_username=actor.username,
        actor_role=actor.role_code,
        object_type="FINDING_EXCEPTION",
        object_id=str(exception_id),
        comment=reason,
        db_path=db_path,
    )


def list_exceptions(
    *,
    active_only: bool = False,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    ensure_exception_state(db_path)
    sql = "select * from finding_exception"
    if active_only:
        sql += " where status = 'ACTIVE'"
    sql += " order by created_at_utc desc, exception_id desc"
    with _connect(db_path) as connection:
        return [dict(row) for row in connection.execute(sql).fetchall()]


def record_export_release(
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
    ensure_exception_state(db_path)
    release_id = "REL_" + uuid.uuid4().hex.upper()
    ids = tuple(sorted({str(value).strip() for value in exception_ids if str(value).strip()}))
    digest = hashlib.sha256(content).hexdigest()
    with _connect(db_path) as connection:
        connection.execute(
            """
            insert into export_release (
                export_release_id, export_kind, export_label, performed_by,
                performed_role, created_at_utc, date_from, date_to,
                exception_count, exception_ids_json, file_name, sha256,
                installation_id, run_id
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                release_id,
                str(export_kind),
                str(export_label),
                actor.username,
                actor.role_code,
                utc_now_text(),
                date_from.isoformat(),
                date_to.isoformat(),
                len(ids),
                json.dumps(ids, ensure_ascii=False),
                str(file_name),
                digest,
                get_installation_id(db_path),
                str(run_id or "").strip(),
            ],
        )
    append_audit_event(
        event_type="CREATE_EXPORT_RELEASE",
        actor_username=actor.username,
        actor_role=actor.role_code,
        object_type="EXPORT_RELEASE",
        object_id=release_id,
        details={
            "export_kind": str(export_kind),
            "export_label": str(export_label),
            "file_name": str(file_name),
            "sha256": digest,
            "exception_ids": ids,
            "run_id": str(run_id or "").strip(),
        },
        db_path=db_path,
    )
    return release_id


def list_export_releases(db_path: Path | str | None = None) -> list[dict[str, Any]]:
    ensure_exception_state(db_path)
    with _connect(db_path) as connection:
        return [
            dict(row)
            for row in connection.execute(
                "select * from export_release order by created_at_utc desc, export_release_id desc"
            ).fetchall()
        ]
