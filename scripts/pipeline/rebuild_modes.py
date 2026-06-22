"""Betriebsmodi fuer den Pipeline-Neuaufbau.

Die Modi bilden bewusst das fachliche Zielbild ab. Der vollstaendige Neuaufbau
ist weiterhin der sichere Standardlauf. Schnelle Teilmodi werden schrittweise
angebunden, sobald sie fachlich isoliert testbar sind.
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
        return self in {
            RebuildMode.FULL_IMPORT_REBUILD,
            RebuildMode.EXPORT_REBUILD,
        }
