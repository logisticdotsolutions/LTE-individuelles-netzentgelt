"""Small runtime overlay that makes the legacy correction form self-explanatory."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Callable, Iterator

import streamlit as st

from manual_override_guidance_module import guidance_for


GUIDED_CORRECTION_RUNTIME_MARKER = "NETZENTGELT_GUIDED_CORRECTION_RUNTIME_PHASE9D_V1_20260610"


@contextmanager
def guided_correction_widgets() -> Iterator[None]:
    """Temporarily improve labels, help text and confirmation in the legacy form."""
    original_selectbox = st.selectbox
    original_text_input = st.text_input
    original_text_area = st.text_area
    original_submit = st.form_submit_button
    original_checkbox = st.checkbox
    state: dict[str, Any] = {"override_type": "", "new_value": "", "confirmed": False, "confirm_rendered": False}

    def guidance():
        kind = str(state.get("override_type") or "SET_PERFORMING_RU")
        return guidance_for(kind)

    def selectbox(label: str, *args: Any, **kwargs: Any):
        if label == "Art der Bearbeitung":
            value = original_selectbox("Was möchtest du korrigieren?", *args, **kwargs)
            state["override_type"] = value
            item = guidance()
            st.info(f"**{item.title}**\n\n{item.purpose}\n\n**Geändertes Feld:** {item.target_field}")
            return value
        if label == "Fachliche Klassifikation" and not guidance().requires_classification:
            return ""
        if label == "Fachliche Klassifikation":
            return original_selectbox(
                "Fachlichen Grund der Unterbrechung auswählen *",
                *args,
                **kwargs,
            )
        return original_selectbox(label, *args, **kwargs)

    def text_input(label: str, *args: Any, **kwargs: Any):
        item = guidance()
        options = dict(kwargs)
        if label == "Transportnummer":
            options.setdefault("help", "Dient zur eindeutigen Zuordnung der betroffenen Bewegungszeile.")
            return original_text_input("Betroffene Transportnummer", *args, **options)
        if label == "Betroffene Loknummer":
            options.setdefault("help", "Das ist die aktuell betroffene Lok. Bei einer Loknummernkorrektur kommt die neue Loknummer in das Feld darunter.")
            return original_text_input("Betroffene bisherige Loknummer", *args, **options)
        if label == "Bisherige Abfahrtszeit zur Eingrenzung":
            options.setdefault("help", "Optional: bestehender Wert zur genaueren Eingrenzung einer einzelnen Bewegungszeile.")
            return original_text_input("Bisherige Abfahrtszeit zur Eingrenzung (optional)", *args, **options)
        if label == "Bisherige Ankunftszeit zur Dokumentation":
            options.setdefault("help", "Optional: bisher dokumentierte Ankunftszeit des Prüffalls.")
            return original_text_input("Bisherige Ankunftszeit zur Dokumentation (optional)", *args, **options)
        if label == "Neuer Wert":
            if not item.requires_new_value:
                st.caption(item.input_help)
                return ""
            options["help"] = f"{item.input_help} Beispiel: {item.example}"
            options.setdefault("placeholder", item.placeholder)
            value = original_text_input(item.input_label, *args, **options)
            state["new_value"] = value
            return value
        return original_text_input(label, *args, **kwargs)

    def text_area(label: str, *args: Any, **kwargs: Any):
        if label == "Begründung / Kommentar":
            item = guidance()
            new_value = str(state.get("new_value") or "Nur Dokumentation / Klassifikation")
            st.markdown("##### Kontrollansicht vor dem Speichern")
            st.info(f"Du änderst **{item.target_field}** auf **{new_value}**. Prüfe diese Auswirkung bewusst.")
            options = dict(kwargs)
            options["placeholder"] = "Warum ist diese konkrete lokale Korrektur fachlich zulässig?"
            options["help"] = "Die Begründung wird gemeinsam mit Benutzer und Zeitstempel im Audit gespeichert."
            return original_text_area("Fachliche Begründung *", *args, **options)
        return original_text_area(label, *args, **kwargs)

    def submit(label: str, *args: Any, **kwargs: Any):
        if label in {"Override speichern", "Speichern und neu prüfen", "Dummy-Lok speichern", "Dummy-Lok speichern und neu prüfen"}:
            if not state["confirm_rendered"]:
                state["confirmed"] = original_checkbox(
                    "Ich habe den aktuellen Wert, den neuen Wert und die Auswirkung fachlich geprüft.",
                    value=False,
                    key="guided_override_confirmation",
                )
                state["confirm_rendered"] = True
            options = dict(kwargs)
            options["disabled"] = bool(options.get("disabled", False) or not state["confirmed"])
            labels = {
                "Override speichern": "Korrektur speichern",
                "Speichern und neu prüfen": "Korrektur speichern und sofort neu prüfen",
                "Dummy-Lok speichern": "Dummy-Lok speichern",
                "Dummy-Lok speichern und neu prüfen": "Dummy-Lok speichern und sofort neu prüfen",
            }
            return original_submit(labels[label], *args, **options)
        return original_submit(label, *args, **kwargs)

    st.selectbox = selectbox
    st.text_input = text_input
    st.text_area = text_area
    st.form_submit_button = submit
    try:
        yield
    finally:
        st.selectbox = original_selectbox
        st.text_input = original_text_input
        st.text_area = original_text_area
        st.form_submit_button = original_submit
