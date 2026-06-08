"""
Netzentgelt MVP - sichere Sammeluebernahme von Systemvorschlaegen
=================================================================

Phase 5D erlaubt es Fachanwendern, mehrere nachvollziehbare Systemvorschlaege
bewusst per Checkmark auszuwaehlen und gesammelt als lokale Overrides zu
speichern. Die Rohdaten bleiben unveraendert. Jeder erzeugte Override besitzt
weiterhin ID, Bearbeiter, Zeitstempel und Kommentar.

Sicherheitsprinzipien
--------------------
- Nur explizit ausgewaehlte Vorschlaege werden gespeichert.
- Ein gemeinsamer Pflichtkommentar ist erforderlich.
- Reine Pruefhinweise ohne Wert oder Klassifikation werden nicht gespeichert.
- Bereits aktive, fachlich identische Overrides werden nicht dupliziert.
- Die Pipeline wird durch dieses Modul nicht automatisch gestartet.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import uuid
from typing import Iterable

import pandas as pd

from manual_override_module import OVERRIDE_COLUMNS


PHASE5D_BATCH_MARKER = "NETZENTGELT_MANUAL_OVERRIDE_PHASE5D_BATCH_V1_20260608"
DOCUMENT_ONLY_TYPES = {"CLASSIFY_GAP", "CASE_NOTE"}
TRANSPORT_REQUIRED_TYPES = {
    "SET_LOCO_NO",
    "SET_PERFORMING_RU",
    "SET_ACTUAL_DEPARTURE",
    "SET_ACTUAL_ARRIVAL",
}


@dataclass(frozen=True)
class BatchSkip:
    suggestion_id: str
    reason: str


@dataclass(frozen=True)
class BatchCreate:
    override_row: dict[str, str]
    suggestion: dict[str, str]


def _clean(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalized_active_flag(value: object) -> str:
    return _clean(value).upper() or "Y"


def _is_active(value: object) -> bool:
    return _normalized_active_flag(value) not in {"N", "NO", "FALSE", "0"}


def _duplicate_key(row: dict[str, object]) -> tuple[str, ...]:
    return (
        _clean(row.get("override_type")).upper(),
        _clean(row.get("transport_number")),
        _clean(row.get("target_loco_no")),
        _clean(row.get("target_actual_departure_utc")),
        _clean(row.get("target_actual_arrival_utc")),
        _clean(row.get("target_source_table")),
        _clean(row.get("target_source_row_id")),
        _clean(row.get("override_value")),
        _clean(row.get("classification_code")).upper(),
    )


def _active_duplicate_keys(overrides: pd.DataFrame) -> set[tuple[str, ...]]:
    if overrides is None or overrides.empty:
        return set()
    result: set[tuple[str, ...]] = set()
    for _, row in overrides.iterrows():
        data = row.to_dict()
        if _is_active(data.get("active_flag")):
            result.add(_duplicate_key(data))
    return result


def is_actionable_suggestion(suggestion: dict[str, object]) -> bool:
    """Nur Vorschlaege mit Wert oder Klassifikation duerfen direkt gespeichert werden."""
    override_type = _clean(suggestion.get("override_type")).upper()
    suggested_value = _clean(suggestion.get("suggested_value"))
    classification_code = _clean(suggestion.get("classification_code"))

    if not override_type:
        return False
    if override_type in DOCUMENT_ONLY_TYPES:
        return bool(suggested_value or classification_code)
    return bool(suggested_value)


def _validate_suggestion(suggestion: dict[str, object]) -> str | None:
    suggestion_id = _clean(suggestion.get("suggestion_id"))
    override_type = _clean(suggestion.get("override_type")).upper()
    suggested_value = _clean(suggestion.get("suggested_value"))
    classification_code = _clean(suggestion.get("classification_code"))
    transport_number = _clean(suggestion.get("transport_number"))

    if not suggestion_id:
        return "Vorschlag-ID fehlt."
    if not override_type:
        return "Override-Typ fehlt."
    if override_type in TRANSPORT_REQUIRED_TYPES and not transport_number:
        return "Transportnummer fehlt fuer diese Korrekturart."
    if override_type in DOCUMENT_ONLY_TYPES:
        if not suggested_value and not classification_code:
            return "Dokumentationsvorschlag enthaelt weder Wert noch Klassifikation."
    elif not suggested_value:
        return "Vorgeschlagener Wert fehlt."
    return None


def suggestion_to_override_row(
    suggestion: dict[str, object],
    *,
    created_by: str,
    comment: str,
    now_text: str | None = None,
    override_id: str | None = None,
) -> dict[str, str]:
    """Einen bestaetigten Systemvorschlag in das stabile Override-Schema ueberfuehren."""
    validation_error = _validate_suggestion(suggestion)
    if validation_error:
        raise ValueError(validation_error)

    now = now_text or _utc_now_text()
    generated_id = override_id or ("OVR_" + uuid.uuid4().hex[:12].upper())
    row = {
        "override_id": generated_id,
        "active_flag": "Y",
        "override_type": _clean(suggestion.get("override_type")).upper(),
        "transport_number": _clean(suggestion.get("transport_number")),
        "target_loco_no": _clean(suggestion.get("loco_no")),
        "target_actual_departure_utc": _clean(suggestion.get("period_start_utc")),
        "target_actual_arrival_utc": _clean(suggestion.get("period_end_utc")),
        "target_source_table": _clean(suggestion.get("source_table")),
        "target_source_row_id": _clean(suggestion.get("source_row_id")),
        "override_value": _clean(suggestion.get("suggested_value")),
        "classification_code": _clean(suggestion.get("classification_code")).upper(),
        "comment": _clean(comment),
        "created_by": _clean(created_by),
        "created_at_utc": now,
        "updated_at_utc": now,
    }
    return {column: _clean(row.get(column)) for column in OVERRIDE_COLUMNS}


def create_overrides_from_selected_suggestions(
    *,
    overrides: pd.DataFrame,
    suggestions: pd.DataFrame,
    selected_suggestion_ids: Iterable[str],
    created_by: str,
    comment: str,
    now_text: str | None = None,
) -> tuple[pd.DataFrame, list[BatchCreate], list[BatchSkip]]:
    """
    Explizit ausgewaehlte Vorschlaege gesammelt in Overrides umwandeln.

    Die Funktion schreibt keine Dateien. Dadurch bleibt die Persistenz in der UI
    atomar und die Logik separat testbar.
    """
    clean_comment = _clean(comment)
    clean_created_by = _clean(created_by)
    if not clean_comment:
        raise ValueError("Bitte eine nachvollziehbare Begruendung erfassen.")
    if not clean_created_by:
        raise ValueError("Bitte einen Bearbeiter erfassen.")

    selected_ids = {_clean(value) for value in selected_suggestion_ids if _clean(value)}
    if not selected_ids:
        raise ValueError("Bitte mindestens einen Vorschlag per Checkmark auswaehlen.")

    base = overrides.copy() if overrides is not None else pd.DataFrame(columns=OVERRIDE_COLUMNS)
    for column in OVERRIDE_COLUMNS:
        if column not in base.columns:
            base[column] = ""
    base = base[list(OVERRIDE_COLUMNS)].fillna("")

    suggestion_rows: dict[str, dict[str, str]] = {}
    if suggestions is not None and not suggestions.empty:
        for _, row in suggestions.iterrows():
            data = {str(key): _clean(value) for key, value in row.to_dict().items()}
            suggestion_id = _clean(data.get("suggestion_id"))
            if suggestion_id:
                suggestion_rows[suggestion_id] = data

    duplicate_keys = _active_duplicate_keys(base)
    created: list[BatchCreate] = []
    skipped: list[BatchSkip] = []
    pending_rows: list[dict[str, str]] = []
    now = now_text or _utc_now_text()

    for suggestion_id in sorted(selected_ids):
        suggestion = suggestion_rows.get(suggestion_id)
        if suggestion is None:
            skipped.append(BatchSkip(suggestion_id, "Vorschlag ist in der aktuellen Liste nicht mehr vorhanden."))
            continue
        if not is_actionable_suggestion(suggestion):
            skipped.append(BatchSkip(suggestion_id, "Reiner Pruefhinweis ohne direkt speicherbaren Wert."))
            continue
        validation_error = _validate_suggestion(suggestion)
        if validation_error:
            skipped.append(BatchSkip(suggestion_id, validation_error))
            continue

        row = suggestion_to_override_row(
            suggestion,
            created_by=clean_created_by,
            comment=clean_comment,
            now_text=now,
        )
        key = _duplicate_key(row)
        if key in duplicate_keys:
            skipped.append(BatchSkip(suggestion_id, "Fachlich identischer aktiver Override ist bereits vorhanden."))
            continue

        duplicate_keys.add(key)
        pending_rows.append(row)
        created.append(BatchCreate(override_row=row, suggestion=suggestion))

    if pending_rows:
        base = pd.concat([base, pd.DataFrame(pending_rows)], ignore_index=True)
        base = base[list(OVERRIDE_COLUMNS)].fillna("")

    return base, created, skipped
