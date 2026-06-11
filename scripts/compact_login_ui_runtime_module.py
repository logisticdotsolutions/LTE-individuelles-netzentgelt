"""Install compact centered authentication views without narrowing the fachliche app."""
from __future__ import annotations
from pathlib import Path

import streamlit as st

from local_auth_module import (
    LocalAuthError,
    UserContext,
    authenticate_user,
    bootstrap_admin,
    change_own_password,
    record_logout,
)

PHASE10C_COMPACT_LOGIN_MARKER = "NETZENTGELT_COMPACT_LOGIN_PHASE10C_V1_20260611"


def _center_column():
    """Return the middle Streamlit column used as a professional login card area."""
    _, center, _ = st.columns([1.15, 1.0, 1.15])
    return center


def install_compact_login_views() -> None:
    """Patch only the authentication screens; keep the authenticated app untouched."""
    import local_auth_ui_module as auth_ui

    if getattr(auth_ui, "_compact_login_views_installed", False):
        return

    def render_bootstrap_admin(db_path: Path) -> None:
        with _center_column():
            st.title("🚆 Bahnstrom Deutschland")
            st.subheader("Ersteinrichtung")
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
            auth_ui._store_user(user)
            st.success("Initialer ADMIN wurde angelegt. Du bist jetzt angemeldet.")
            st.rerun()

    def render_login(db_path: Path) -> None:
        with _center_column():
            st.title("🚆 Bahnstrom Deutschland")
            st.subheader("Anmeldung")
            st.caption("Lokale, auditierbare Anmeldung für die operative Prüfung und Exportvorbereitung.")
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
            auth_ui._store_user(result.user)
            st.rerun()

    def render_required_password_change(user: UserContext, db_path: Path) -> None:
        with _center_column():
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
                auth_ui._store_user(updated)
                st.success("Passwort wurde geändert.")
                st.rerun()
            if st.button("Abmelden", key="local_auth_password_change_logout"):
                record_logout(user, db_path)
                auth_ui._clear_session()
                st.rerun()
            st.stop()

    auth_ui._render_bootstrap_admin = render_bootstrap_admin
    auth_ui._render_login = render_login
    auth_ui._render_required_password_change = render_required_password_change
    auth_ui._compact_login_views_installed = True
