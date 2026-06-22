from __future__ import annotations

import streamlit as st


_REPLACEMENTS = (
    (
        "Lokale, auditierbare Anmeldung für die operative Prüfung und Exportvorbereitung.",
        "Tagesprüfung und Exporte",
    ),
    (
        "Operative Prüfung und Exportvorbereitung für das individuelle Netzentgelt.",
        "Tagesprüfung und Exportvorbereitung.",
    ),
    (
        "Die Auswahl wirkt ausschließlich auf die UKL-Exporte.",
        "Nur für UKL-Exporte. RailCube bleibt unverändert.",
    ),
    (
        "Diese Listen sind direkt in die Fallbearbeitung integriert.",
        "Prüfhilfen zur fachlichen Sichtung. Keine automatische Änderung.",
    ),
    (
        "Für DE-relevante GAPs über 120 Minuten wird in der Fallbearbeitung",
        "DE-relevante GAPs über 120 Minuten werden als Prüfvorschlag markiert.",
    ),
)


def _compact_text(value: object) -> object:
    if not isinstance(value, str):
        return value
    for prefix, replacement in _REPLACEMENTS:
        if value.startswith(prefix):
            return replacement
    return value


def install_compact_copy_runtime() -> None:
    """Shorten selected verbose captions without changing any fachliche behavior."""
    if getattr(st, "_lte_compact_copy_installed", False):
        return

    original_caption = st.caption

    def compact_caption(body, *args, **kwargs):
        return original_caption(_compact_text(body), *args, **kwargs)

    st.caption = compact_caption
    st._lte_compact_copy_installed = True
