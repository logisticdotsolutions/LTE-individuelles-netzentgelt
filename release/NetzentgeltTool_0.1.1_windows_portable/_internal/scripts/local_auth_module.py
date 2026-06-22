"""
Portable local login and audit state for the Netzentgelt MVP.

The module intentionally keeps all mutable authentication state in a local
SQLite database. It is designed for the temporary single-installation pilot.
A later Entra-ID or central SQL migration can replace this adapter without
changing the fachliche Streamlit application.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import base64
import hashlib
import hmac
import json
from pathlib import Path
import re
import secrets
import sqlite3
from typing import Any
import uuid


PHASE9A_AUTH_MARKER = "NETZENTGELT_PORTABLE_LOCAL_AUTH_PHASE9A_V1_20260610"
ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / "data" / "02_duckdb" / "app_state"
DEFAULT_DB_PATH = STATE_DIR / "netzentgelt_app_state.sqlite"
PASSWORD_SCHEME = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 310_000
PASSWORD_MIN_LENGTH = 12
ALLOWED_ROLES = ("ADMIN", "LTE_DE", "LTE_NL")
USERNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")


class LocalAuthError(RuntimeError):
    """Understandable error for invalid local authentication actions."""


@dataclass(frozen=True)
class UserContext:
    username: str
    display_name: str
    role_code: str
    installation_id: str
    must_change_password: bool = False

    @property
    def is_admin(self) -> bool:
        return self.role_code == "ADMIN"

    def to_session_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AuthenticationResult:
    success: bool
    user: UserContext | None
    reason: str


def utc_now_text() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_username(value: object) -> str:
    return str(value or "").strip().lower()


def validate_username(username: str) -> str:
    normalized = normalize_username(username)
    if not USERNAME_PATTERN.fullmatch(normalized):
        raise LocalAuthError(
            "Der Benutzername muss 3 bis 64 Zeichen lang sein und darf nur "
            "Kleinbuchstaben, Ziffern, Punkt, Unterstrich und Bindestrich enthalten."
        )
    return normalized


def validate_password(password: str) -> None:
    value = str(password or "")
    if len(value) < PASSWORD_MIN_LENGTH:
        raise LocalAuthError(
            f"Das Passwort muss mindestens {PASSWORD_MIN_LENGTH} Zeichen lang sein."
        )
    if value.lower() == value or value.upper() == value:
        raise LocalAuthError("Das Passwort muss Groß- und Kleinbuchstaben enthalten.")
    if not any(character.isdigit() for character in value):
        raise LocalAuthError("Das Passwort muss mindestens eine Ziffer enthalten.")


def validate_role(role_code: str) -> str:
    normalized = str(role_code or "").strip().upper()
    if normalized not in ALLOWED_ROLES:
        raise LocalAuthError(
            "Unzulässige Rolle. Erlaubt sind: " + ", ".join(ALLOWED_ROLES)
        )
    return normalized


def hash_password(password: str) -> str:
    validate_password(password)
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_ITERATIONS,
    )
    return "$".join(
        [
            PASSWORD_SCHEME,
            str(PASSWORD_ITERATIONS),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        ]
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, iterations_text, salt_text, digest_text = str(encoded).split("$", 3)
        if scheme != PASSWORD_SCHEME:
            return False
        iterations = int(iterations_text)
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
    except (ValueError, TypeError):
        return False

    actual = hashlib.pbkdf2_hmac(
        "sha256",
        str(password or "").encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(actual, expected)


def _db_path(db_path: Path | str | None = None) -> Path:
    return Path(db_path or DEFAULT_DB_PATH).resolve()


def _connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    path = _db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("pragma foreign_keys = on")
    connection.execute("pragma busy_timeout = 5000")
    connection.execute("pragma journal_mode = wal")
    connection.execute("pragma synchronous = normal")
    return connection


def _ensure_meta(connection: sqlite3.Connection, key: str, value: str) -> None:
    now = utc_now_text()
    connection.execute(
        """
        insert into app_meta(meta_key, meta_value, updated_at_utc)
        values (?, ?, ?)
        on conflict(meta_key) do nothing
        """,
        [key, value, now],
    )


def ensure_app_state(db_path: Path | str | None = None) -> Path:
    path = _db_path(db_path)
    with _connect(path) as connection:
        connection.executescript(
            """
            create table if not exists app_meta (
                meta_key text primary key,
                meta_value text not null,
                updated_at_utc text not null
            );

            create table if not exists app_user (
                username text primary key,
                display_name text not null,
                password_hash text not null,
                role_code text not null check (role_code in ('ADMIN', 'LTE_DE', 'LTE_NL')),
                active_flag integer not null default 1 check (active_flag in (0, 1)),
                must_change_password integer not null default 0 check (must_change_password in (0, 1)),
                created_by text not null,
                created_at_utc text not null,
                updated_by text not null,
                updated_at_utc text not null
            );

            create table if not exists audit_event (
                audit_event_id text primary key,
                event_type text not null,
                actor_username text not null,
                actor_role text,
                occurred_at_utc text not null,
                installation_id text not null,
                object_type text,
                object_id text,
                comment text,
                details_json text not null
            );

            create index if not exists idx_audit_event_occurred
                on audit_event(occurred_at_utc desc);
            create index if not exists idx_audit_event_actor
                on audit_event(actor_username, occurred_at_utc desc);
            """
        )
        _ensure_meta(connection, "schema_version", "1")
        _ensure_meta(connection, "installation_id", str(uuid.uuid4()))
        _ensure_meta(connection, "created_at_utc", utc_now_text())
    return path


def get_meta(key: str, db_path: Path | str | None = None) -> str:
    ensure_app_state(db_path)
    with _connect(db_path) as connection:
        row = connection.execute(
            "select meta_value from app_meta where meta_key = ?",
            [str(key)],
        ).fetchone()
    return str(row["meta_value"]) if row else ""


def get_installation_id(db_path: Path | str | None = None) -> str:
    return get_meta("installation_id", db_path)


def has_users(db_path: Path | str | None = None) -> bool:
    ensure_app_state(db_path)
    with _connect(db_path) as connection:
        return bool(connection.execute("select count(*) from app_user").fetchone()[0])


def _row_to_user(row: sqlite3.Row, installation_id: str) -> UserContext:
    return UserContext(
        username=str(row["username"]),
        display_name=str(row["display_name"]),
        role_code=str(row["role_code"]),
        installation_id=installation_id,
        must_change_password=bool(row["must_change_password"]),
    )


def get_user(username: str, db_path: Path | str | None = None) -> UserContext | None:
    normalized = normalize_username(username)
    if not normalized:
        return None
    installation_id = get_installation_id(db_path)
    with _connect(db_path) as connection:
        row = connection.execute(
            """
            select username, display_name, role_code, must_change_password
            from app_user
            where username = ? and active_flag = 1
            """,
            [normalized],
        ).fetchone()
    return _row_to_user(row, installation_id) if row else None


def append_audit_event(
    *,
    event_type: str,
    actor_username: str,
    actor_role: str | None = None,
    object_type: str | None = None,
    object_id: str | None = None,
    comment: str | None = None,
    details: dict[str, Any] | None = None,
    db_path: Path | str | None = None,
) -> str:
    ensure_app_state(db_path)
    event_id = "AUD_" + uuid.uuid4().hex.upper()
    with _connect(db_path) as connection:
        installation_id = connection.execute(
            "select meta_value from app_meta where meta_key = 'installation_id'"
        ).fetchone()[0]
        connection.execute(
            """
            insert into audit_event (
                audit_event_id, event_type, actor_username, actor_role,
                occurred_at_utc, installation_id, object_type, object_id,
                comment, details_json
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                event_id,
                str(event_type or "").strip().upper(),
                normalize_username(actor_username) or "anonymous",
                str(actor_role or "").strip().upper() or None,
                utc_now_text(),
                str(installation_id),
                str(object_type or "").strip() or None,
                str(object_id or "").strip() or None,
                str(comment or "").strip() or None,
                json.dumps(details or {}, ensure_ascii=False, sort_keys=True),
            ],
        )
    return event_id


def bootstrap_admin(
    *,
    username: str,
    display_name: str,
    password: str,
    db_path: Path | str | None = None,
) -> UserContext:
    ensure_app_state(db_path)
    if has_users(db_path):
        raise LocalAuthError("Der Bootstrap-Admin kann nur beim ersten Start angelegt werden.")

    normalized = validate_username(username)
    display = str(display_name or "").strip()
    if not display:
        raise LocalAuthError("Bitte einen Anzeigenamen erfassen.")

    now = utc_now_text()
    password_hash = hash_password(password)
    with _connect(db_path) as connection:
        connection.execute(
            """
            insert into app_user (
                username, display_name, password_hash, role_code, active_flag,
                must_change_password, created_by, created_at_utc, updated_by, updated_at_utc
            ) values (?, ?, ?, 'ADMIN', 1, 0, 'bootstrap', ?, 'bootstrap', ?)
            """,
            [normalized, display, password_hash, now, now],
        )
    user = get_user(normalized, db_path)
    if user is None:
        raise LocalAuthError("Der Bootstrap-Admin konnte nicht geladen werden.")
    append_audit_event(
        event_type="BOOTSTRAP_ADMIN_CREATED",
        actor_username=user.username,
        actor_role=user.role_code,
        object_type="APP_USER",
        object_id=user.username,
        comment="Initialer lokaler Admin wurde beim ersten Start angelegt.",
        db_path=db_path,
    )
    return user


def authenticate_user(
    *,
    username: str,
    password: str,
    db_path: Path | str | None = None,
) -> AuthenticationResult:
    ensure_app_state(db_path)
    normalized = normalize_username(username)
    with _connect(db_path) as connection:
        row = connection.execute(
            """
            select username, display_name, password_hash, role_code,
                   active_flag, must_change_password
            from app_user
            where username = ?
            """,
            [normalized],
        ).fetchone()

    if row is None or not bool(row["active_flag"]):
        append_audit_event(
            event_type="LOGIN_FAILED",
            actor_username=normalized or "anonymous",
            comment="Unbekannter oder deaktivierter Benutzer.",
            db_path=db_path,
        )
        return AuthenticationResult(False, None, "Benutzername oder Passwort ist ungültig.")

    if not verify_password(password, str(row["password_hash"])):
        append_audit_event(
            event_type="LOGIN_FAILED",
            actor_username=normalized,
            actor_role=str(row["role_code"]),
            comment="Ungültiges Passwort.",
            db_path=db_path,
        )
        return AuthenticationResult(False, None, "Benutzername oder Passwort ist ungültig.")

    user = _row_to_user(row, get_installation_id(db_path))
    append_audit_event(
        event_type="LOGIN_SUCCESS",
        actor_username=user.username,
        actor_role=user.role_code,
        db_path=db_path,
    )
    return AuthenticationResult(True, user, "")


def record_logout(user: UserContext, db_path: Path | str | None = None) -> None:
    append_audit_event(
        event_type="LOGOUT",
        actor_username=user.username,
        actor_role=user.role_code,
        db_path=db_path,
    )


def _require_admin(actor: UserContext) -> None:
    if not actor.is_admin:
        raise LocalAuthError("Diese Aktion ist ausschließlich für ADMIN zulässig.")


def create_user(
    *,
    actor: UserContext,
    username: str,
    display_name: str,
    password: str,
    role_code: str,
    must_change_password: bool = True,
    db_path: Path | str | None = None,
) -> UserContext:
    _require_admin(actor)
    normalized = validate_username(username)
    display = str(display_name or "").strip()
    if not display:
        raise LocalAuthError("Bitte einen Anzeigenamen erfassen.")
    role = validate_role(role_code)
    password_hash = hash_password(password)
    now = utc_now_text()

    try:
        with _connect(db_path) as connection:
            connection.execute(
                """
                insert into app_user (
                    username, display_name, password_hash, role_code, active_flag,
                    must_change_password, created_by, created_at_utc, updated_by, updated_at_utc
                ) values (?, ?, ?, ?, 1, ?, ?, ?, ?, ?)
                """,
                [
                    normalized,
                    display,
                    password_hash,
                    role,
                    1 if must_change_password else 0,
                    actor.username,
                    now,
                    actor.username,
                    now,
                ],
            )
    except sqlite3.IntegrityError as error:
        raise LocalAuthError(f"Benutzer {normalized} existiert bereits.") from error

    append_audit_event(
        event_type="CREATE_USER",
        actor_username=actor.username,
        actor_role=actor.role_code,
        object_type="APP_USER",
        object_id=normalized,
        details={"role_code": role, "must_change_password": bool(must_change_password)},
        db_path=db_path,
    )
    created = get_user(normalized, db_path)
    if created is None:
        raise LocalAuthError("Der neu angelegte Benutzer konnte nicht geladen werden.")
    return created


def assign_role(
    *,
    actor: UserContext,
    username: str,
    role_code: str,
    db_path: Path | str | None = None,
) -> None:
    _require_admin(actor)
    normalized = validate_username(username)
    role = validate_role(role_code)
    with _connect(db_path) as connection:
        existing = connection.execute(
            "select role_code from app_user where username = ?",
            [normalized],
        ).fetchone()
        if existing is None:
            raise LocalAuthError(f"Benutzer {normalized} wurde nicht gefunden.")
        old_role = str(existing["role_code"])
        if old_role == "ADMIN" and role != "ADMIN":
            admin_count = int(
                connection.execute(
                    "select count(*) from app_user where role_code = 'ADMIN' and active_flag = 1"
                ).fetchone()[0]
            )
            if admin_count <= 1:
                raise LocalAuthError("Der letzte aktive ADMIN darf nicht herabgestuft werden.")
        connection.execute(
            """
            update app_user
            set role_code = ?, updated_by = ?, updated_at_utc = ?
            where username = ?
            """,
            [role, actor.username, utc_now_text(), normalized],
        )
    append_audit_event(
        event_type="ASSIGN_ROLE",
        actor_username=actor.username,
        actor_role=actor.role_code,
        object_type="APP_USER",
        object_id=normalized,
        details={"old_role": old_role, "new_role": role},
        db_path=db_path,
    )


def set_user_active(
    *,
    actor: UserContext,
    username: str,
    active: bool,
    db_path: Path | str | None = None,
) -> None:
    _require_admin(actor)
    normalized = validate_username(username)
    with _connect(db_path) as connection:
        existing = connection.execute(
            "select role_code, active_flag from app_user where username = ?",
            [normalized],
        ).fetchone()
        if existing is None:
            raise LocalAuthError(f"Benutzer {normalized} wurde nicht gefunden.")
        if normalized == actor.username and not active:
            raise LocalAuthError("Der aktuell angemeldete ADMIN darf sich nicht selbst deaktivieren.")
        if str(existing["role_code"]) == "ADMIN" and bool(existing["active_flag"]) and not active:
            admin_count = int(
                connection.execute(
                    "select count(*) from app_user where role_code = 'ADMIN' and active_flag = 1"
                ).fetchone()[0]
            )
            if admin_count <= 1:
                raise LocalAuthError("Der letzte aktive ADMIN darf nicht deaktiviert werden.")
        connection.execute(
            """
            update app_user
            set active_flag = ?, updated_by = ?, updated_at_utc = ?
            where username = ?
            """,
            [1 if active else 0, actor.username, utc_now_text(), normalized],
        )
    append_audit_event(
        event_type="ENABLE_USER" if active else "DISABLE_USER",
        actor_username=actor.username,
        actor_role=actor.role_code,
        object_type="APP_USER",
        object_id=normalized,
        db_path=db_path,
    )


def reset_password(
    *,
    actor: UserContext,
    username: str,
    new_password: str,
    must_change_password: bool = True,
    db_path: Path | str | None = None,
) -> None:
    _require_admin(actor)
    normalized = validate_username(username)
    password_hash = hash_password(new_password)
    with _connect(db_path) as connection:
        updated = connection.execute(
            """
            update app_user
            set password_hash = ?, must_change_password = ?,
                updated_by = ?, updated_at_utc = ?
            where username = ?
            """,
            [
                password_hash,
                1 if must_change_password else 0,
                actor.username,
                utc_now_text(),
                normalized,
            ],
        ).rowcount
    if not updated:
        raise LocalAuthError(f"Benutzer {normalized} wurde nicht gefunden.")
    append_audit_event(
        event_type="RESET_PASSWORD",
        actor_username=actor.username,
        actor_role=actor.role_code,
        object_type="APP_USER",
        object_id=normalized,
        details={"must_change_password": bool(must_change_password)},
        db_path=db_path,
    )


def change_own_password(
    *,
    user: UserContext,
    old_password: str,
    new_password: str,
    db_path: Path | str | None = None,
) -> UserContext:
    result = authenticate_user(username=user.username, password=old_password, db_path=db_path)
    if not result.success:
        raise LocalAuthError("Das aktuelle Passwort ist nicht korrekt.")
    password_hash = hash_password(new_password)
    with _connect(db_path) as connection:
        connection.execute(
            """
            update app_user
            set password_hash = ?, must_change_password = 0,
                updated_by = ?, updated_at_utc = ?
            where username = ?
            """,
            [password_hash, user.username, utc_now_text(), user.username],
        )
    append_audit_event(
        event_type="CHANGE_OWN_PASSWORD",
        actor_username=user.username,
        actor_role=user.role_code,
        object_type="APP_USER",
        object_id=user.username,
        db_path=db_path,
    )
    updated = get_user(user.username, db_path)
    if updated is None:
        raise LocalAuthError("Benutzer konnte nach Passwortänderung nicht geladen werden.")
    return updated


def list_users(db_path: Path | str | None = None) -> list[dict[str, Any]]:
    ensure_app_state(db_path)
    with _connect(db_path) as connection:
        rows = connection.execute(
            """
            select username, display_name, role_code, active_flag,
                   must_change_password, created_by, created_at_utc,
                   updated_by, updated_at_utc
            from app_user
            order by role_code, username
            """
        ).fetchall()
    return [dict(row) for row in rows]


def list_audit_events(
    *,
    limit: int = 500,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    ensure_app_state(db_path)
    safe_limit = max(1, min(int(limit), 10_000))
    with _connect(db_path) as connection:
        rows = connection.execute(
            """
            select audit_event_id, event_type, actor_username, actor_role,
                   occurred_at_utc, installation_id, object_type, object_id,
                   comment, details_json
            from audit_event
            order by occurred_at_utc desc, audit_event_id desc
            limit ?
            """,
            [safe_limit],
        ).fetchall()
    return [dict(row) for row in rows]
