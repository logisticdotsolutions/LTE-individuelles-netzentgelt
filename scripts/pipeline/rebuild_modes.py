"""Betriebsmodi fuer den Pipeline-Neuaufbau.

Die Modi bilden bewusst das fachliche Zielbild ab. Im ersten Schritt ist nur
der vollstaendige Neuaufbau produktiv angebunden. Die schnelleren Modi werden
in den naechsten Refactorings schrittweise implementiert.
"""

from enum import Enum


class RebuildMode(str, Enum):
    """Unterstuetzte Zielmodi der Berechnungspipeline."""

    FULL_IMPORT_REBUILD = "FULL_IMPORT_REBUILD"
    FULL_REBUILD_FROM_RAW = "FULL_REBUILD_FROM_RAW"
    OVERRIDE_REBUILD = "OVERRIDE_REBUILD"
    EXPORT_REBUILD = "EXPORT_REBUILD"

    @property
    def is_implemented(self) -> bool:
        """True, wenn der Modus aktuell technisch angebunden ist."""
        return self is RebuildMode.FULL_IMPORT_REBUILD
