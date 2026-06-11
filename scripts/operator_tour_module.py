"""Guided sidebar tour for operators."""
from __future__ import annotations
import streamlit as st

PHASE10A_OPERATOR_TOUR_MARKER = "NETZENTGELT_OPERATOR_GUIDED_TOUR_PHASE10A_V1_20260611"
_ACTIVE = "operator_tour_active"
_STEP = "operator_tour_step"
_STEPS = (
    ("Start", "Aktualisiere zuerst die Daten. Danach wechselst du zu '2. Offene Aufgaben'."),
    ("Aufgaben", "Wähle unter einer Aufgabenliste eine Lok und klicke auf 'Fall öffnen'. Merken oder Kopieren ist nicht nötig."),
    ("Fall prüfen", "Im Fall siehst du Zeitachse, Grenzübertritte, Stehzeiten, GAPs und Hinweise gemeinsam."),
    ("Fall bearbeiten", "Dokumentiere Korrekturen oder klassifiziere eine Unterbrechung, zum Beispiel als mögliche kalte Abstellung."),
    ("Ausnahme", "Eine begründete Export-Ausnahme hebt nur die Sperre auf. Der Fehler bleibt sichtbar und auditierbar."),
    ("Export", "Erstelle den Export erst nach der fachlichen Prüfung."),
)

def render_operator_tour_sidebar() -> None:
    st.sidebar.markdown("### Hilfe")
    if not bool(st.session_state.get(_ACTIVE, False)):
        if st.sidebar.button("▶️ Tour starten", key="operator_tour_start", use_container_width=True):
            st.session_state[_ACTIVE] = True
            st.session_state[_STEP] = 0
            st.rerun()
        return
    step = max(0, min(int(st.session_state.get(_STEP, 0)), len(_STEPS) - 1))
    title, body = _STEPS[step]
    st.sidebar.info(f"**Tour {step + 1}/{len(_STEPS)} · {title}**\n\n{body}")
    left, right = st.sidebar.columns(2)
    with left:
        if st.button("← Zurück", key="operator_tour_back", disabled=step == 0, use_container_width=True):
            st.session_state[_STEP] = step - 1
            st.rerun()
    with right:
        if st.button("Weiter →", key="operator_tour_next", disabled=step == len(_STEPS) - 1, use_container_width=True):
            st.session_state[_STEP] = step + 1
            st.rerun()
    if st.sidebar.button("⏹ Tour abbrechen", key="operator_tour_stop", use_container_width=True):
        st.session_state[_ACTIVE] = False
        st.session_state.pop(_STEP, None)
        st.rerun()
    st.sidebar.divider()
