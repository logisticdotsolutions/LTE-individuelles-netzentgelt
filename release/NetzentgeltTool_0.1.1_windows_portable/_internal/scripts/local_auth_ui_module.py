"""Streamlit UI for the portable local login and administration layer."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from local_auth_module import (
    ALLOWED_ROLES,
    DEFAULT_DB_PATH,
    LocalAuthError,
    UserContext,
    append_audit_event,
    assign_role,
    authenticate_user,
    bootstrap_admin,
    change_own_password,
    create_user,
    ensure_app_state,
    get_installation_id,
    has_users,
    list_audit_events,
    list_users,
    record_logout,
    reset_password,
    set_user_active,
)


PHASE9A_AUTH_UI_MARKER = "NETZENTGELT_PORTABLE_LOCAL_AUTH_UI_PHASE9A_V1_20260610"
SESSION_USER_KEY = "local_auth_user"
SESSION_ADMIN_MODE_KEY = "local_auth_admin_mode"


def _session_user() -> UserContext | None:
    payload = st.session_state.get(SESSION_USER_KEY)
    if not isinstance(payload, dict):
        return None
    try:
        return UserContext(
            username=str(payload["username"]),
            display_name=str(payload["display_name"]),
            role_code=str(payload["role_code"]),
            installation_id=str(payload["installation_id"]),
            must_change_password=bool(payload.get("must_change_password", False)),
        )
    except (KeyError, TypeError, ValueError):
        return None


def get_current_user() -> UserContext | None:
    """Return the authenticated Streamlit session user, if available."""
    return _session_user()


def require_current_user() -> UserContext:
    user = _session_user()
    if user is None:
        raise RuntimeError("Kein angemeldeter Benutzer in der Streamlit-Session vorhanden.")
    return user


def _store_user(user: UserContext) -> None:
    st.session_state[SESSION_USER_KEY] = asdict(user)


def _clear_session() -> None:
    for key in [SESSION_USER_KEY, SESSION_ADMIN_MODE_KEY]:
        st.session_state.pop(key, None)


def _render_bootstrap_admin(db_path: Path) -> None:
    st.title("🚆 Bahnstrom Deutschland - Ersteinrichtung")
    st.info(
        "Für diese lokale Installation existiert noch kein Benutzer. "
        "Lege einmalig den initialen ADMIN an. Passwörter werden ausschließlich gehasht gespeichert."
    )
    with st.form("local_auth_bootstrap_admin"):
        username = st.text_input("Admin-Benutzername", placeholder="christoph.orgl")
        display_name = st.text_input("Anzeigename", placeholder="Christoph Orgl")
        password = st.text_input("Passwort", type="password")
        password_repeat = st.text_input("Passwort wiederholen", type="password")
        submitted = st.form_submit_button("Initialen ADMIN anlegen", type="primary")

    if not submitted:
        st.stop()
    if password != password_repeat:
        st.error("Die beiden Passwörter stimmen nicht überein.")
        st.stop()
    try:
        user = bootstrap_admin(
            username=username,
            display_name=display_name,
            password=password,
            db_path=db_path,
        )
    except LocalAuthError as error:
        st.error(str(error))
        st.stop()

    _store_user(user)
    st.success("Initialer ADMIN wurde angelegt. Du bist jetzt angemeldet.")
    st.rerun()


def _render_login(db_path: Path) -> None:
    st.title("🚆 Bahnstrom Deutschland - Anmeldung")
    st.caption(
        "Lokale, auditierbare Anmeldung für die operative Prüfung und Exportvorbereitung."
    )
    with st.form("local_auth_login"):
        username = st.text_input("Benutzername")
        password = st.text_input("Passwort", type="password")
        submitted = st.form_submit_button("Anmelden", type="primary")

    if not submitted:
        st.stop()

    result = authenticate_user(username=username, password=password, db_path=db_path)
    if not result.success or result.user is None:
        st.error(result.reason)
        st.stop()

    _store_user(result.user)
    st.rerun()


def _render_required_password_change(user: UserContext, db_path: Path) -> None:
    st.title("🔐 Passwort ändern")
    st.warning(
        "Für dieses Benutzerkonto ist vor der ersten fachlichen Nutzung ein persönliches Passwort erforderlich."
    )
    with st.form("local_auth_required_password_change"):
        old_password = st.text_input("Aktuelles Passwort", type="password")
        new_password = st.text_input("Neues Passwort", type="password")
        new_password_repeat = st.text_input("Neues Passwort wiederholen", type="password")
        submitted = st.form_submit_button("Passwort ändern", type="primary")

    if submitted:
        if new_password != new_password_repeat:
            st.error("Die beiden neuen Passwörter stimmen nicht überein.")
            st.stop()
        try:
            updated = change_own_password(
                user=user,
                old_password=old_password,
                new_password=new_password,
                db_path=db_path,
            )
        except LocalAuthError as error:
            st.error(str(error))
            st.stop()
        _store_user(updated)
        st.success("Passwort wurde geändert.")
        st.rerun()

    if st.button("Abmelden", key="local_auth_password_change_logout"):
        record_logout(user, db_path)
        _clear_session()
        st.rerun()
    st.stop()


def require_local_login(db_path: Path | str | None = None) -> UserContext:
    """Gate the application until a local user has authenticated."""
    path = ensure_app_state(db_path or DEFAULT_DB_PATH)
    if not has_users(path):
        _render_bootstrap_admin(path)

    user = _session_user()
    if user is None:
        _render_login(path)

    user = require_current_user()
    if user.must_change_password:
        _render_required_password_change(user, path)
    return user


def render_authenticated_sidebar(user: UserContext, db_path: Path | str | None = None) -> bool:
    """Show identity, role and logout. Return whether the admin page should open."""
    path = Path(db_path or DEFAULT_DB_PATH)
    st.sidebar.markdown("### Angemeldet")
    st.sidebar.write(f"**{user.display_name}**")
    st.sidebar.caption(f"Benutzer: {user.username}")
    st.sidebar.caption(f"Rolle: {user.role_code}")
    st.sidebar.caption(f"Installation: {user.installation_id[:8]}…")

    admin_mode = False
    if user.is_admin:
        admin_mode = st.sidebar.toggle(
            "⚙️ Admin-Bereich öffnen",
            value=bool(st.session_state.get(SESSION_ADMIN_MODE_KEY, False)),
            key=SESSION_ADMIN_MODE_KEY,
        )

    if st.sidebar.button("Abmelden", key="local_auth_logout", use_container_width=True):
        record_logout(user, path)
        _clear_session()
        st.rerun()

    st.sidebar.divider()
    return admin_mode


def _render_create_user(actor: UserContext, db_path: Path) -> None:
    st.markdown("#### Benutzer anlegen")
    with st.form("local_auth_admin_create_user", clear_on_submit=True):
        username = st.text_input("Benutzername", placeholder="vorname.nachname")
        display_name = st.text_input("Anzeigename")
        role_code = st.selectbox("Rolle", list(ALLOWED_ROLES), index=1)
        password = st.text_input("Temporäres Passwort", type="password")
        password_repeat = st.text_input("Temporäres Passwort wiederholen", type="password")
        must_change_password = st.checkbox("Passwortwechsel bei erster Anmeldung erzwingen", value=True)
        submitted = st.form_submit_button("Benutzer anlegen", type="primary")

    if not submitted:
        return
    if password != password_repeat:
        st.error("Die beiden Passwörter stimmen nicht überein.")
        return
    try:
        created = create_user(
            actor=actor,
            username=username,
            display_name=display_name,
            password=password,
            role_code=role_code,
            must_change_password=must_change_password,
            db_path=db_path,
        )
    except LocalAuthError as error:
        st.error(str(error))
        return
    st.success(f"Benutzer {created.username} wurde mit Rolle {created.role_code} angelegt.")
    st.rerun()


def _render_manage_user(actor: UserContext, db_path: Path) -> None:
    users = list_users(db_path)
    st.markdown("#### Bestehende Benutzer")
    if not users:
        st.info("Keine Benutzer vorhanden.")
        return

    display = pd.DataFrame(users).rename(
        columns={
            "username": "Benutzername",
            "display_name": "Anzeigename",
            "role_code": "Rolle",
            "active_flag": "Aktiv",
            "must_change_password": "Passwortwechsel erforderlich",
            "created_by": "Angelegt durch",
            "created_at_utc": "Angelegt am",
            "updated_by": "Geändert durch",
            "updated_at_utc": "Geändert am",
        }
    )
    st.dataframe(display, use_container_width=True, hide_index=True)

    usernames = [str(user["username"]) for user in users]
    selected_username = st.selectbox("Benutzer bearbeiten", usernames, key="local_auth_admin_selected_user")
    selected = next(user for user in users if str(user["username"]) == selected_username)

    col_role, col_active = st.columns(2)
    with col_role:
        role_options = list(ALLOWED_ROLES)
        current_role = str(selected["role_code"])
        selected_role = st.selectbox(
            "Rolle ändern",
            role_options,
            index=role_options.index(current_role),
            key="local_auth_admin_new_role",
        )
        if st.button("Rolle speichern", key="local_auth_admin_save_role", use_container_width=True):
            try:
                assign_role(actor=actor, username=selected_username, role_code=selected_role, db_path=db_path)
            except LocalAuthError as error:
                st.error(str(error))
            else:
                st.success("Rolle wurde aktualisiert.")
                st.rerun()

    with col_active:
        is_active = bool(selected["active_flag"])
        st.write("Aktueller Status: " + ("aktiv" if is_active else "deaktiviert"))
        if st.button(
            "Benutzer deaktivieren" if is_active else "Benutzer aktivieren",
            key="local_auth_admin_toggle_active",
            use_container_width=True,
        ):
            try:
                set_user_active(
                    actor=actor,
                    username=selected_username,
                    active=not is_active,
                    db_path=db_path,
                )
            except LocalAuthError as error:
                st.error(str(error))
            else:
                st.success("Benutzerstatus wurde aktualisiert.")
                st.rerun()

    with st.expander("Passwort zurücksetzen", expanded=False):
        with st.form("local_auth_admin_reset_password"):
            new_password = st.text_input("Neues temporäres Passwort", type="password")
            new_password_repeat = st.text_input("Neues temporäres Passwort wiederholen", type="password")
            must_change_password = st.checkbox("Passwortwechsel bei nächster Anmeldung erzwingen", value=True)
            submitted = st.form_submit_button("Passwort zurücksetzen")
        if submitted:
            if new_password != new_password_repeat:
                st.error("Die beiden Passwörter stimmen nicht überein.")
            else:
                try:
                    reset_password(
                        actor=actor,
                        username=selected_username,
                        new_password=new_password,
                        must_change_password=must_change_password,
                        db_path=db_path,
                    )
                except LocalAuthError as error:
                    st.error(str(error))
                else:
                    st.success("Passwort wurde zurückgesetzt.")
                    st.rerun()


def _render_audit_log(db_path: Path) -> None:
    st.markdown("#### Audit Trail")
    st.caption(
        "Der lokale Audit Trail dokumentiert Anmeldungen, Benutzerverwaltung und spätere fachliche Schreibaktionen."
    )
    limit = st.number_input("Maximale Auditzeilen", min_value=100, max_value=10_000, value=500, step=100)
    events = list_audit_events(limit=int(limit), db_path=db_path)
    if not events:
        st.info("Noch keine Audit-Ereignisse vorhanden.")
        return
    data = pd.DataFrame(events).rename(
        columns={
            "audit_event_id": "Audit-ID",
            "event_type": "Aktion",
            "actor_username": "Benutzer",
            "actor_role": "Rolle",
            "occurred_at_utc": "Zeitpunkt UTC",
            "installation_id": "Installation",
            "object_type": "Objekttyp",
            "object_id": "Objekt-ID",
            "comment": "Kommentar",
            "details_json": "Details",
        }
    )
    st.dataframe(data, use_container_width=True, hide_index=True)
    st.download_button(
        "Audit Trail als CSV herunterladen",
        data=data.to_csv(index=False, sep=";").encode("utf-8-sig"),
        file_name="netzentgelt_audit_trail.csv",
        mime="text/csv",
    )


def render_admin_area(actor: UserContext, db_path: Path | str | None = None) -> None:
    """Render the local ADMIN area instead of the fachliche main app."""
    if not actor.is_admin:
        st.error("Der Admin-Bereich ist ausschließlich für ADMIN verfügbar.")
        st.stop()
    path = ensure_app_state(db_path or DEFAULT_DB_PATH)
    st.title("⚙️ Admin-Bereich")
    st.caption("Lokale Benutzerverwaltung und revisionssicherer Audit Trail für diese Installation.")

    info_1, info_2, info_3 = st.columns(3)
    info_1.metric("Installation", get_installation_id(path)[:8] + "…")
    info_2.metric("Benutzer", len(list_users(path)))
    info_3.metric("Rollen", len(ALLOWED_ROLES))

    tab_users, tab_audit, tab_info = st.tabs(["Benutzerverwaltung", "Audit Trail", "Systeminfo"])
    with tab_users:
        _render_create_user(actor, path)
        st.divider()
        _render_manage_user(actor, path)
    with tab_audit:
        _render_audit_log(path)
    with tab_info:
        st.markdown("#### Lokaler Pilotbetrieb")
        st.info(
            "Diese Installation arbeitet bewusst lokal. Benutzer, Rollen und Audit-Ereignisse werden nicht automatisch "
            "mit anderen Rechnern synchronisiert. Mehrfachzuordnungen werden in der Übergangsphase durch UKL behandelt."
        )
        st.code(str(path), language="text")
        st.caption(f"Marker: {PHASE9A_AUTH_UI_MARKER}")
