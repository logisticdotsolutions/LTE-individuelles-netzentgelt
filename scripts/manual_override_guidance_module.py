"""Guidance metadata and validation for the controller-friendly correction UI."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

import pandas as pd


GUIDED_CORRECTION_UX_MARKER = "NETZENTGELT_GUIDED_CORRECTION_UX_PHASE9D_V2_20260610"


@dataclass(frozen=True)
class CorrectionGuidance:
    title: str
    purpose: str
    target_field: str
    input_label: str
    input_help: str
    placeholder: str
    example: str
    requires_new_value: bool = True
    requires_transport: bool = False
    requires_classification: bool = False
    requires_loco: bool = False


GUIDANCE_BY_TYPE = {
    "SET_PERFORMING_RU": CorrectionGuidance(
        title="Nutzendes EVU korrigieren",
        purpose="Ersetzt für den ausgewählten Transport das nutzende EVU (PerformingRU).",
        target_field="PerformingRU / nutzendes EVU",
        input_label="Neues nutzendes EVU (PerformingRU) *",
        input_help="Trage die vollständige EVU-Bezeichnung ein, die für diesen Transport gelten soll.",
        placeholder="z. B. LTE DE - LTE Germany GmbH",
        example="LTE DE - LTE Germany GmbH",
        requires_transport=True,
    ),
    "SET_LOCO_NO": CorrectionGuidance(
        title="Loknummer korrigieren oder ergänzen",
        purpose="Ersetzt eine falsche Loknummer oder ergänzt eine fehlende Loknummer für den ausgewählten Transport.",
        target_field="Loknummer",
        input_label="Neue Loknummer *",
        input_help="Trage die fachlich richtige Loknummer ein. Bei fehlender Loknummer wird sie ergänzt.",
        placeholder="z. B. 91806189201-7",
        example="91806189201-7",
        requires_transport=True,
    ),
    "SET_SEQUENCE_TS": CorrectionGuidance(
        title="Grenzzeitanker korrigieren",
        purpose="Ersetzt den fachlichen Zeitanker eines Grenzereignisses in der Lok-Zeitachse.",
        target_field="Grenzzeitanker / Border Time",
        input_label="Neuer Grenzzeitanker (UTC) *",
        input_help="Verwende Datum und Uhrzeit. Die Zeit wird als UTC-Zeitanker verarbeitet.",
        placeholder="z. B. 2026-06-07 14:30:00",
        example="2026-06-07 14:30:00",
    ),
    "SET_ACTUAL_DEPARTURE": CorrectionGuidance(
        title="Abfahrtszeit korrigieren",
        purpose="Ersetzt die tatsächliche Abfahrtszeit (ActualDeparture) des ausgewählten Transports.",
        target_field="ActualDeparture / tatsächliche Abfahrtszeit",
        input_label="Neue Abfahrtszeit (UTC) *",
        input_help="Trage die fachlich richtige tatsächliche Abfahrtszeit ein.",
        placeholder="z. B. 2026-06-07 08:15:00",
        example="2026-06-07 08:15:00",
        requires_transport=True,
    ),
    "SET_ACTUAL_ARRIVAL": CorrectionGuidance(
        title="Ankunftszeit korrigieren",
        purpose="Ersetzt die tatsächliche Ankunftszeit (ActualArrival) des ausgewählten Transports.",
        target_field="ActualArrival / tatsächliche Ankunftszeit",
        input_label="Neue Ankunftszeit (UTC) *",
        input_help="Trage die fachlich richtige tatsächliche Ankunftszeit ein.",
        placeholder="z. B. 2026-06-07 11:45:00",
        example="2026-06-07 11:45:00",
        requires_transport=True,
    ),
    "CLASSIFY_GAP": CorrectionGuidance(
        title="Unterbrechung fachlich einordnen",
        purpose="Dokumentiert den fachlichen Grund einer Unterbrechung. Die Zeitachse wird dadurch nicht automatisch verändert.",
        target_field="Fachliche GAP-Klassifikation",
        input_label="Kein neuer technischer Wert erforderlich",
        input_help="Wähle unten den fachlichen Grund der Unterbrechung aus.",
        placeholder="",
        example="Mögliche kalte Abstellung",
        requires_new_value=False,
        requires_classification=True,
        requires_loco=True,
    ),
    "CASE_NOTE": CorrectionGuidance(
        title="Bearbeitungsnotiz hinterlegen",
        purpose="Speichert ausschließlich eine nachvollziehbare Notiz zum Prüffall. Es wird kein Quelldatenwert verändert.",
        target_field="Dokumentation / Bearbeitungsnotiz",
        input_label="Kein neuer technischer Wert erforderlich",
        input_help="Beschreibe die fachliche Feststellung im Kommentarfeld.",
        placeholder="",
        example="Fall geprüft; Datenkorrektur in RailCube beauftragt.",
        requires_new_value=False,
    ),
    "MARK_DUMMY_LOCOMOTIVE": CorrectionGuidance(
        title="Als Dummy-/Planungslok markieren",
        purpose="Nimmt die ausgewählte Loknummer in den lokalen Dummy-Katalog auf. Die Markierung gilt für künftige Prüfungen dieser lokalen Installation.",
        target_field="Loknummer im lokalen Dummy-Katalog",
        input_label="Keine zusätzliche Werteingabe erforderlich",
        input_help="Prüfe die betroffene Loknummer und begründe die Markierung.",
        placeholder="",
        example="Dummy-Lok aus Planungssystem",
        requires_new_value=False,
        requires_loco=True,
    ),
    "ADJUST_OVERLAP": CorrectionGuidance(
        title="Zeitliche Überschneidung anpassen",
        purpose=(
            "Korrigiert Abfahrts- oder Ankunftszeiten beider überschneidender Transporte, "
            "um die Zeitüberschneidung aufzulösen. Felder, die leer bleiben, werden nicht gespeichert."
        ),
        target_field="ActualDeparture / ActualArrival beider überschneidenden Transporte",
        input_label="Zeitkorrekturen werden in der Tabelle erfasst",
        input_help=(
            "Trage die korrigierten Zeitwerte in die Korrekturspalte ein. "
            "Leere Korrekturspalten werden nicht als Korrektur gespeichert."
        ),
        placeholder="",
        example="2026-06-09 11:00:00",
        requires_new_value=False,
        requires_transport=True,
    ),
}


VALUE_COLUMN_CANDIDATES = {
    "SET_PERFORMING_RU": ("performing_ru", "PerformingRU", "CurrentContractant"),
    "SET_LOCO_NO": ("loco_no", "LocomotiveNo", "locomotive_no"),
    "SET_SEQUENCE_TS": ("sequence_ts", "Border Time", "border_time", "period_start_utc"),
    "SET_ACTUAL_DEPARTURE": ("actual_departure_ts", "ActualDeparture", "actual_departure_utc", "period_start_utc"),
    "SET_ACTUAL_ARRIVAL": ("actual_arrival_ts", "ActualArrival", "actual_arrival_utc", "period_end_utc"),
}


TIME_VALUE_TYPES = {"SET_SEQUENCE_TS", "SET_ACTUAL_DEPARTURE", "SET_ACTUAL_ARRIVAL"}
_NON_VALUES = {
    "",
    "Nicht vorhanden / nicht eindeutig",
    "Keine technische Wertänderung",
    "Aus dem ausgewählten Prüffall ableiten / fachlich prüfen",
}


def _clean(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def guidance_for(override_type: str) -> CorrectionGuidance:
    return GUIDANCE_BY_TYPE[str(override_type or "").strip().upper()]


def _pick_column(columns: Iterable[object], candidates: Iterable[str]) -> str | None:
    by_lower = {str(column).lower(): str(column) for column in columns}
    for candidate in candidates:
        if candidate.lower() in by_lower:
            return by_lower[candidate.lower()]
    return None


def matching_timeline_rows(
    timeline: pd.DataFrame,
    *,
    transport_number: str = "",
    loco_no: str = "",
) -> pd.DataFrame:
    """Return the most useful timeline rows for a selected correction case."""
    if timeline is None or timeline.empty:
        return pd.DataFrame()
    result = timeline.copy()
    transport_column = _pick_column(result.columns, ("transport_number", "TransportNumber", "TransportNo"))
    loco_column = _pick_column(result.columns, ("loco_no", "LocomotiveNo", "locomotive_no"))

    if transport_number and transport_column:
        match = result[transport_column].fillna("").astype(str).str.strip().eq(str(transport_number).strip())
        if match.any():
            return result.loc[match].copy()
    if loco_no and loco_column:
        match = result[loco_column].fillna("").astype(str).str.strip().eq(str(loco_no).strip())
        if match.any():
            return result.loc[match].copy()
    return pd.DataFrame()


def current_value_for(
    override_type: str,
    timeline: pd.DataFrame,
    *,
    transport_number: str = "",
    loco_no: str = "",
    fallback_start: str = "",
    fallback_end: str = "",
) -> str:
    """Return a readable current-value summary for the selected correction."""
    kind = str(override_type or "").strip().upper()
    rows = matching_timeline_rows(timeline, transport_number=transport_number, loco_no=loco_no)
    column = _pick_column(rows.columns, VALUE_COLUMN_CANDIDATES.get(kind, ())) if not rows.empty else None
    values: list[str] = []
    if column:
        values = sorted({_clean(value) for value in rows[column].tolist() if _clean(value)})

    if values:
        if len(values) <= 3:
            return " | ".join(values)
        return " | ".join(values[:3]) + f" | … ({len(values)} Werte)"
    if kind == "SET_LOCO_NO":
        return _clean(loco_no) or "Nicht vorhanden / nicht eindeutig"
    if kind in {"SET_SEQUENCE_TS", "SET_ACTUAL_DEPARTURE"}:
        return _clean(fallback_start) or "Nicht vorhanden / nicht eindeutig"
    if kind == "SET_ACTUAL_ARRIVAL":
        return _clean(fallback_end) or "Nicht vorhanden / nicht eindeutig"
    return "Nicht vorhanden / nicht eindeutig"


def _normalized_value(override_type: str, value: object) -> str:
    """Normalize one value for no-op comparison without changing stored text."""
    kind = str(override_type or "").strip().upper()
    text = _clean(value)
    if not text:
        return ""
    if kind in TIME_VALUE_TYPES:
        parsed = pd.to_datetime(text, errors="coerce", utc=True)
        if not pd.isna(parsed):
            return pd.Timestamp(parsed).isoformat()
    return re.sub(r"\s+", " ", text).casefold()


def is_noop_value(override_type: str, current_value: object, new_value: object) -> bool:
    """Return True only when a technical correction would not change a value."""
    guidance = guidance_for(override_type)
    current = _clean(current_value)
    proposed = _clean(new_value)
    if not guidance.requires_new_value or current in _NON_VALUES or not proposed:
        return False
    if " | " in current or "…" in current:
        return False
    return _normalized_value(override_type, current) == _normalized_value(override_type, proposed)


def validate_guided_input(
    *,
    override_type: str,
    transport_number: str,
    target_loco_no: str,
    override_value: str,
    classification_code: str,
    comment: str,
    confirmed: bool,
    current_value: str = "",
) -> list[str]:
    """Return controller-friendly validation messages for one correction form."""
    kind = str(override_type or "").strip().upper()
    guidance = guidance_for(kind)
    errors: list[str] = []
    if guidance.requires_transport and not str(transport_number or "").strip():
        errors.append("Bitte eine Transportnummer erfassen. Ohne Transportnummer ist die Zielzeile nicht eindeutig genug.")
    if guidance.requires_loco and not str(target_loco_no or "").strip():
        errors.append("Bitte die betroffene Loknummer erfassen.")
    if guidance.requires_new_value and not str(override_value or "").strip():
        errors.append(f"Bitte das Feld „{guidance.input_label.replace(' *', '')}“ ausfüllen.")
    if is_noop_value(kind, current_value, override_value):
        errors.append("Der neue Wert entspricht bereits dem aktuell erkannten Wert. Es besteht keine tatsächliche Änderung.")
    if guidance.requires_classification and not str(classification_code or "").strip():
        errors.append("Bitte den fachlichen Grund der Unterbrechung auswählen.")
    if kind in TIME_VALUE_TYPES and str(override_value or "").strip():
        if pd.isna(pd.to_datetime(str(override_value).strip(), errors="coerce", utc=True)):
            errors.append(f"Bitte eine gültige Zeit eingeben, zum Beispiel: {guidance.example}.")
    if len(str(comment or "").strip()) < 10:
        errors.append("Bitte eine nachvollziehbare Begründung mit mindestens 10 Zeichen erfassen.")
    if not confirmed:
        errors.append("Bitte bestätige, dass du den aktuellen Wert und die Auswirkung geprüft hast.")
    return errors
