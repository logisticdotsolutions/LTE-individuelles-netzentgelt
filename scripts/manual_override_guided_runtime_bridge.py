"""Small runtime overlay that makes the legacy correction form self-explanatory."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any, Iterator

import pandas as pd
import streamlit as st

from manual_override_guidance_module import current_value_for, guidance_for, is_noop_value
from manual_override_widget_value_module import (
    EMPTY_DROPDOWN_VALUE,
    combine_utc_picker_value,
    parse_utc_picker_default,
    performing_ru_options,
)


GUIDED_CORRECTION_RUNTIME_MARKER = "NETZENTGELT_GUIDED_CORRECTION_RUNTIME_PHASE9D_V5_20260610"
_TIME_CORRECTION_TYPES = {"SET_SEQUENCE_TS", "SET_ACTUAL_DEPARTURE", "SET_ACTUAL_ARRIVAL"}


@contextmanager
def guided_correction_widgets(timeline: pd.DataFrame | None = None) -> Iterator[None]:
    """Temporarily improve labels, visibility, controlled inputs and confirmation."""
    original_selectbox = st.selectbox
    original_text_input = st.text_input
    original_text_area = st.text_area
    original_submit = st.form_submit_button
    original_checkbox = st.checkbox
    state: dict[str, Any] = {
        "override_type": "",
        "new_value": "",
        "transport_number": "",
        "target_loco_no": "",
        "departure": "",
        "arrival": "",
        "confirmed": False,
        "confirm_rendered": False,
        "context_rendered": False,
        "noop": False,
    }

    def guidance():
        kind = str(state.get("override_type") or "SET_PERFORMING_RU")
        return guidance_for(kind)

    def hidden_value(options: dict[str, Any]) -> str:
        return str(options.get("value") or "")

    def current_value() -> str:
        kind = str(state.get("override_type") or "")
        if kind in {"CLASSIFY_GAP", "CASE_NOTE", "MARK_DUMMY_LOCOMOTIVE"}:
            return "Keine technische Wertänderung"
        return current_value_for(
            kind,
            timeline if isinstance(timeline, pd.DataFrame) else pd.DataFrame(),
            transport_number=str(state.get("transport_number") or ""),
            loco_no=str(state.get("target_loco_no") or ""),
            fallback_start=str(state.get("departure") or ""),
            fallback_end=str(state.get("arrival") or ""),
        )

    def update_noop(new_value: object) -> bool:
        state["noop"] = is_noop_value(
            str(state.get("override_type") or ""),
            current_value(),
            new_value,
        )
        return bool(state["noop"])

    def render_context() -> None:
        if state["context_rendered"]:
            return
        item = guidance()
        st.markdown("##### Aktueller Kontext")
        st.caption("Diese Angaben grenzen den betroffenen Datensatz ein. Nur das unten bezeichnete Zielfeld wird ersetzt.")
        st.table(
            pd.DataFrame(
                [
                    {"Angabe": "Betroffene Transportnummer", "Aktueller Kontext": str(state.get("transport_number") or "-")},
                    {"Angabe": "Betroffene bisherige Loknummer", "Aktueller Kontext": str(state.get("target_loco_no") or "-")},
                    {"Angabe": "Bisherige Abfahrtszeit", "Aktueller Kontext": str(state.get("departure") or "-")},
                    {"Angabe": "Bisherige Ankunftszeit", "Aktueller Kontext": str(state.get("arrival") or "-")},
                    {"Angabe": "Tatsächlich zu änderndes Feld", "Aktueller Kontext": item.target_field},
                    {"Angabe": "Aktuell erkannter Wert", "Aktueller Kontext": current_value()},
                ]
            )
        )
        state["context_rendered"] = True

    def render_noop_warning() -> None:
        if state["noop"]:
            st.warning(
                "Der neue Wert entspricht bereits dem aktuell erkannten Wert. "
                "Es würde keine tatsächliche Änderung gespeichert. Bitte wähle einen abweichenden Wert."
            )

    def controlled_performing_ru(suggested: str) -> str:
        current = current_value()
        options = performing_ru_options(
            timeline if isinstance(timeline, pd.DataFrame) else pd.DataFrame(),
            current_value=current,
            suggested_value=suggested,
        )
        default = suggested if suggested in options and not is_noop_value("SET_PERFORMING_RU", current, suggested) else EMPTY_DROPDOWN_VALUE
        if suggested and default == EMPTY_DROPDOWN_VALUE:
            st.warning(
                "Der automatisch vorgeschlagene Wert entspricht bereits dem aktuell erkannten Wert. "
                "Es ist keine Korrektur vorausgewählt."
            )
        selected = original_selectbox(
            "Neues nutzendes EVU (PerformingRU) *",
            options,
            index=options.index(default),
            help="Wähle ein EVU aus der konsistenten Liste. Freitext ist bewusst nicht zulässig.",
            key="guided_override_performing_ru_select",
        )
        return "" if selected == EMPTY_DROPDOWN_VALUE else str(selected)

    def controlled_utc_timestamp(kind: str, suggested: str) -> str:
        current = current_value()
        base = parse_utc_picker_default(suggested) or parse_utc_picker_default(current) or datetime.now().replace(microsecond=0)
        if suggested and is_noop_value(kind, current, suggested):
            st.warning(
                "Der automatisch vorgeschlagene Zeitwert entspricht bereits dem aktuell erkannten Wert. "
                "Bitte ändere Datum oder Uhrzeit nur, wenn fachlich wirklich ein anderer Wert gelten soll."
            )
        col_date, col_time = st.columns(2)
        with col_date:
            selected_day = st.date_input(
                "Neues Datum (UTC) *",
                value=base.date(),
                format="YYYY-MM-DD",
                key=f"guided_override_new_date_{kind}",
            )
        with col_time:
            selected_time = st.time_input(
                "Neue Uhrzeit (UTC) *",
                value=base.time(),
                step=timedelta(seconds=1),
                key=f"guided_override_new_time_{kind}",
            )
        value = combine_utc_picker_value(selected_day, selected_time)
        st.caption(f"Gespeicherter UTC-Wert: `{value}`")
        return value

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
            render_context()
            return original_selectbox("Fachlichen Grund der Unterbrechung auswählen *", *args, **kwargs)
        return original_selectbox(label, *args, **kwargs)

    def text_input(label: str, *args: Any, **kwargs: Any):
        item = guidance()
        kind = str(state.get("override_type") or "")
        options = dict(kwargs)
        if label == "Transportnummer":
            value = hidden_value(options)
            state["transport_number"] = value
            if kind not in {"SET_PERFORMING_RU", "SET_LOCO_NO", "SET_ACTUAL_DEPARTURE", "SET_ACTUAL_ARRIVAL", "SET_SEQUENCE_TS", "CASE_NOTE"}:
                return value
            options.setdefault("help", "Dient zur eindeutigen Zuordnung der betroffenen Bewegungszeile.")
            value = original_text_input("Betroffene Transportnummer", *args, **options)
            state["transport_number"] = value
            return value
        if label == "Betroffene Loknummer":
            value = hidden_value(options)
            state["target_loco_no"] = value
            if kind not in {"SET_LOCO_NO", "SET_SEQUENCE_TS", "CLASSIFY_GAP", "CASE_NOTE", "MARK_DUMMY_LOCOMOTIVE"}:
                return value
            options.setdefault("help", "Das ist die aktuell betroffene Lok. Bei einer Loknummernkorrektur kommt die neue Loknummer in das Feld darunter.")
            value = original_text_input("Betroffene bisherige Loknummer", *args, **options)
            state["target_loco_no"] = value
            return value
        if label == "Bisherige Abfahrtszeit zur Eingrenzung":
            value = hidden_value(options)
            state["departure"] = value
            if kind not in {"SET_SEQUENCE_TS", "SET_ACTUAL_DEPARTURE", "SET_ACTUAL_ARRIVAL", "CASE_NOTE"}:
                return value
            options.setdefault("help", "Optional: bestehender Wert zur genaueren Eingrenzung einer einzelnen Bewegungszeile.")
            value = original_text_input("Bisherige Abfahrtszeit zur Eingrenzung (optional)", *args, **options)
            state["departure"] = value
            return value
        if label == "Bisherige Ankunftszeit zur Dokumentation":
            value = hidden_value(options)
            state["arrival"] = value
            if kind not in {"SET_SEQUENCE_TS", "SET_ACTUAL_ARRIVAL", "CASE_NOTE"}:
                return value
            options.setdefault("help", "Optional: bisher dokumentierte Ankunftszeit des Prüffalls.")
            value = original_text_input("Bisherige Ankunftszeit zur Dokumentation (optional)", *args, **options)
            state["arrival"] = value
            return value
        if label == "Neuer Wert":
            render_context()
            if not item.requires_new_value:
                st.caption(item.input_help)
                return ""
            suggested = hidden_value(options)
            if kind == "SET_PERFORMING_RU":
                value = controlled_performing_ru(suggested)
            elif kind in _TIME_CORRECTION_TYPES:
                value = controlled_utc_timestamp(kind, suggested)
            else:
                if is_noop_value(kind, current_value(), suggested):
                    options["value"] = ""
                    st.warning(
                        "Der automatisch vorgeschlagene Wert entspricht bereits dem aktuell erkannten Wert. "
                        "Es ist keine Korrektur vorausgefüllt."
                    )
                options["help"] = f"{item.input_help} Beispiel: {item.example}"
                options.setdefault("placeholder", item.placeholder)
                value = original_text_input(item.input_label, *args, **options)
            state["new_value"] = value
            update_noop(value)
            render_noop_warning()
            return value
        return original_text_input(label, *args, **kwargs)

    def text_area(label: str, *args: Any, **kwargs: Any):
        if label == "Begründung / Kommentar":
            render_context()
            item = guidance()
            new_value = str(state.get("new_value") or "Noch kein abweichender Wert erfasst")
            st.markdown("##### Kontrollansicht vor dem Speichern")
            st.table(
                pd.DataFrame(
                    [{"Zu änderndes Feld": item.target_field, "Aktueller Wert": current_value(), "Neuer Wert / neue Einordnung": new_value}]
                )
            )
            render_noop_warning()
            st.info("Prüfe diese Gegenüberstellung bewusst. Erst danach darf die lokale Korrektur gespeichert werden.")
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
            labels = {
                "Override speichern": "Korrektur speichern",
                "Speichern und neu prüfen": "Korrektur speichern und sofort neu prüfen",
                "Dummy-Lok speichern": "Dummy-Lok speichern",
                "Dummy-Lok speichern und neu prüfen": "Dummy-Lok speichern und sofort neu prüfen",
            }
            clicked = original_submit(labels[label], *args, **options)
            if not clicked:
                return False
            if not state["confirmed"]:
                st.error("Bitte bestätige, dass du den aktuellen Wert, den neuen Wert und die Auswirkung fachlich geprüft hast.")
                return False
            if guidance().requires_new_value and not str(state.get("new_value") or "").strip():
                st.error("Bitte wähle oder erfasse zuerst einen tatsächlich neuen Wert.")
                return False
            if state["noop"]:
                st.error("Der neue Wert entspricht bereits dem aktuell erkannten Wert. Es besteht keine tatsächliche Änderung.")
                return False
            return True
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
