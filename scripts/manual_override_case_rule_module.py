"""Readable rule metadata and conservative correction defaults for the operator UI."""
from __future__ import annotations

PHASE10E_CASE_RULE_METADATA_MARKER = "NETZENTGELT_CASE_RULE_METADATA_PHASE10E_V1_20260611"

RULE_DESCRIPTIONS = {
    "R001": "Erste Bewegung der Lok-Zeitachse ohne Vorgänger",
    "R002": "Abfahrtszeit fehlt oder ist nicht auswertbar",
    "R003": "Ankunftszeit fehlt oder ist nicht auswertbar",
    "R007": "Nutzendes EVU / PerformingRU ist nicht eindeutig zuordenbar",
    "R010": "Nachverfolgung endet oder Ortskette ist unterbrochen",
    "R010.5": "Unterbrechung der Ortskette ab acht Stunden",
    "R011": "Zeitliche Überschneidung von Lokbewegungen",
    "R012": "Loknummer fehlt oder ist eine technische Dummy-/Planungslok",
    "GAP": "Unterbrechung in der Lok-Zeitachse",
}

# Only unambiguous rules receive an automatic default. Ambiguous findings remain manual.
DEFAULT_OVERRIDE_BY_RULE = {
    "R002": "SET_ACTUAL_DEPARTURE",
    "R003": "SET_ACTUAL_ARRIVAL",
    "R007": "SET_PERFORMING_RU",
    "R010": "CLASSIFY_GAP",
    "R010.5": "CLASSIFY_GAP",
    "R011": "ADJUST_OVERLAP",
    "R012": "SET_LOCO_NO",
    "GAP": "CLASSIFY_GAP",
}


def normalize_rule_id(rule_id: object) -> str:
    """Normalize legacy spellings such as R12 to the canonical R012 form."""
    value = str(rule_id or "").strip().upper()
    aliases = {
        "R1": "R001",
        "R2": "R002",
        "R3": "R003",
        "R7": "R007",
        "R10": "R010",
        "R10.5": "R010.5",
        "R11": "R011",
        "R12": "R012",
    }
    return aliases.get(value, value)


def rule_description(rule_id: object) -> str:
    """Return a readable description while retaining unknown rule identifiers."""
    normalized = normalize_rule_id(rule_id)
    return RULE_DESCRIPTIONS.get(normalized, "Prüffall aus dem fachlichen Regelwerk")


def format_case_option(option: object) -> str:
    """Add the readable rule description to one raw case-select option."""
    text = str(option or "").strip()
    if not text or text == "Freie manuelle Erfassung":
        return text
    rule, separator, remainder = text.partition(" | ")
    normalized = normalize_rule_id(rule)
    if not separator:
        return f"{normalized} – {rule_description(normalized)}"
    return f"{normalized} – {rule_description(normalized)} | {remainder}"


def rule_id_from_case_option(option: object) -> str:
    """Extract the canonical rule id from one raw case-select option."""
    text = str(option or "").strip()
    if not text or text == "Freie manuelle Erfassung":
        return ""
    return normalize_rule_id(text.partition(" | ")[0])


def default_override_type_for_rule(rule_id: object) -> str:
    """Return a safe automatic correction default only for unambiguous rules."""
    return DEFAULT_OVERRIDE_BY_RULE.get(normalize_rule_id(rule_id), "")
