from __future__ import annotations

from dataclasses import dataclass


STATUS_HARDENED = "HARDENED_UI_EXPORT"
STATUS_PARTIAL = "PARTIAL"
STATUS_NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
STATUS_EXTERNAL = "EXTERNAL_PROCESS"
STATUS_DEPRECATED = "DEPRECATED_TECHNICAL_ONLY"


@dataclass(frozen=True)
class UKLComplianceContract:
    code: str
    role: str
    artifact: str
    status: str
    blocking_gap: bool
    note: str


CONTRACTS = (
    UKLComplianceContract(
        code="HOLDER_Z01",
        role="HALTER",
        artifact="Vorlage_Zuordnungen.xlsx / Z01",
        status=STATUS_PARTIAL,
        blocking_gap=True,
        note=(
            "Zwei LTE-Holding-Dateien und lokale Preflight-Prüfung sind vorhanden. "
            "Die vEns-Ableitung muss jedoch von statischer Lok-default_vens auf eine "
            "zeit- und nutzerbezogene Zuordnung umgestellt werden."
        ),
    ),
    UKLComplianceContract(
        code="HOLDER_H01",
        role="HALTER",
        artifact="Vorlage_Halterschaft.xlsx / H01",
        status=STATUS_NOT_IMPLEMENTED,
        blocking_gap=True,
        note="Eigenständiger Halterschaftsexport und Zeitachsenprüfung fehlen.",
    ),
    UKLComplianceContract(
        code="HOLDER_DAILY_ZDSL",
        role="HALTER",
        artifact="Tägliche Zuordnungsdatensatzliste und 10-Werktage-Korrekturfenster",
        status=STATUS_PARTIAL,
        blocking_gap=True,
        note=(
            "Z01-Dateien können für Zeiträume erstellt werden. Automatisierte tägliche "
            "Meldetag-Steuerung, Änderungsdetektion und Versandüberwachung fehlen."
        ),
    ),
    UKLComplianceContract(
        code="USER_N01",
        role="NUTZER",
        artifact="Vorlage_Übernahmeanfrage,Übergabemeldung.xlsx / N01",
        status=STATUS_PARTIAL,
        blocking_gap=True,
        note=(
            "Aktuelle Fünf-Spalten-Vorlage und Preflight sind aktiv. Die Empfängerzuordnung "
            "zu einem der beiden Holding-Mandanten muss fachlich eindeutig je Fall ableitbar sein."
        ),
    ),
    UKLComplianceContract(
        code="USER_AE01",
        role="NUTZER",
        artifact="Vorlage_Aufenthaltsereignis.xlsx / AE01",
        status=STATUS_PARTIAL,
        blocking_gap=True,
        note=(
            "Gemappte vEns und Preflight sind aktiv. Ortsvalidierung gegen RIL-Codes und "
            "vollständige fachliche Abnahme fehlen noch."
        ),
    ),
    UKLComplianceContract(
        code="USER_AV01",
        role="NUTZER",
        artifact="Vorlage_Aufenthaltsabschnitt.xlsx / AV01",
        status=STATUS_PARTIAL,
        blocking_gap=True,
        note=(
            "Implementiert in av01_export_module.py. Quelle: core_loco_timeline MOVEMENT-Zeilen. "
            "Netzstatus-Ableitung analog AE01. Ortsvalidierung gegen RIL-Codes und "
            "vollständige fachliche Abnahme stehen noch aus."
        ),
    ),
    UKLComplianceContract(
        code="USER_T01",
        role="NUTZER",
        artifact="Vorlage_Traktionsleistungen.xlsx / T01",
        status=STATUS_PARTIAL,
        blocking_gap=True,
        note=(
            "Implementiert in t01_export_module.py. Quelle: raw_locomotivemovement mit DE-Filter. "
            "Anreicherung via t01_mapping_module (Bestellkriterium, Verwendungsart, Höchstgeschwindigkeit). "
            "Vollständige fachliche Abnahme inklusive Gewichtsberechnung steht noch aus."
        ),
    ),
    UKLComplianceContract(
        code="USER_AB01",
        role="NUTZER",
        artifact="Vorlage_Abstellungen.xlsx / AB01",
        status=STATUS_NOT_IMPLEMENTED,
        blocking_gap=True,
        note="Abstellungen fehlen; GAP-120-Vorschläge sind nur Vorbereitung.",
    ),
    UKLComplianceContract(
        code="PROCESS_AS4",
        role="PROZESS",
        artifact="AS4-Kommunikation oder KoDi-Anbindung",
        status=STATUS_NOT_IMPLEMENTED,
        blocking_gap=True,
        note="Versandweg und KoDi-Betriebsprozess fehlen im MVP.",
    ),
    UKLComplianceContract(
        code="PROCESS_QUITTUNGEN",
        role="PROZESS",
        artifact="Meldungs- und Quittungsstatus",
        status=STATUS_NOT_IMPLEMENTED,
        blocking_gap=True,
        note="Quittungen, Versionierung und Ablehnungsbearbeitung fehlen im MVP.",
    ),
    UKLComplianceContract(
        code="AUDIT_SOURCE_ROW_HASH",
        role="AUDIT",
        artifact="Persistierter source_row_hash",
        status=STATUS_NOT_IMPLEMENTED,
        blocking_gap=False,
        note="Bereits als W001 in der Testsuite sichtbar; Integration in Staging und Audit fehlt.",
    ),
    UKLComplianceContract(
        code="LEGACY_N01_CSV",
        role="TECHNIK",
        artifact="data/03_exports/export_nutzungsmeldung.csv",
        status=STATUS_DEPRECATED,
        blocking_gap=False,
        note=(
            "Pipeline-CSV verwendet noch den alten Sechs-Spalten-Vertrag. Nicht als UKL-Uploaddatei "
            "verwenden. Produktive UI nutzt ausschließlich den gehärteten N01-XLSX-Pfad."
        ),
    ),
)


def contracts_by_role(role: str) -> tuple[UKLComplianceContract, ...]:
    normalized = str(role).strip().upper()
    return tuple(contract for contract in CONTRACTS if contract.role == normalized)


def blocking_gaps() -> tuple[UKLComplianceContract, ...]:
    return tuple(contract for contract in CONTRACTS if contract.blocking_gap)


def is_fully_compliant() -> bool:
    """Vollständige UKL-Erfüllung erst melden, wenn kein blockierender Gap mehr offen ist."""
    return not blocking_gaps()
