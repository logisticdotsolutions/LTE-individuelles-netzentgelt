# Automatischer Import der DB-Energie-Marktpartner-IDs

Stand: 2026-06-12

## Zweck

Der Importer lädt die offiziell veröffentlichte Marktpartner-ID-Liste der DB Energie für das Bahnstromnetz herunter und erzeugt eine lokale, auditierbare Referenzdatei. Die Liste enthält insbesondere die Rollen `ANU_VENS` und `ANE_TENS`, aber auch weitere Marktrollen wie Dienstleister, Netzbetreiber und Messdienstleister.

Die Marktpartner-ID-Liste ersetzt **nicht** die separate zeitabhängige vEns-Zuordnung. Eine vEns darf nicht aus einer Marktpartner-ID, einem Firmennamen oder einer Loknummer abgeleitet werden.

## Start

Einmalig nach neuen Python-Abhängigkeiten:

```powershell
.\RUN_TESTS.bat -InstallDependencies
```

Import ausführen:

```powershell
.\RUN_IMPORT_MP_IDS.bat
```

## Offizielle Quelle

Der Importer verwendet die öffentliche DB-Energie-Datei:

```text
https://www.dbenergie.de/resource/blob/4570920/ce260c87155d7495c47acd35cd0dae29/Datei-Marktpartner-IDs-PDF-data.pdf
```

Die URL ist zentral in `scripts/mp_id_import_module.py` hinterlegt.

## Erzeugte lokale Dateien

Aktuelle Referenz:

```text
data/01_mapping/public_market_partner_ids.csv
```

Audit-Snapshot je Lauf:

```text
data/04_audit/mp_id_imports/<UTC-TIMESTAMP>/source.pdf
data/04_audit/mp_id_imports/<UTC-TIMESTAMP>/delta.csv
data/04_audit/mp_id_imports/<UTC-TIMESTAMP>/metadata.json
```

Die Dateien werden lokal erzeugt und sind in `.gitignore` ausgeschlossen.

## Delta-Status

| Status | Bedeutung |
|---|---|
| `NEW` | Neue Kombination aus Marktrolle und Marktpartner-ID |
| `CHANGED` | Unternehmensname zur bekannten Rolle und ID wurde geändert |
| `REMOVED` | Eintrag war zuvor vorhanden, fehlt aber im aktuellen offiziellen Dokument |
| `UNCHANGED` | Keine Änderung |

## Audit-Metadaten

`metadata.json` enthält:

- Quell-URL
- Dokumentstand aus der PDF
- SHA-256 der heruntergeladenen PDF
- Importzeitpunkt in UTC
- Anzahl der Einträge
- Anzahl je Delta-Status

## Abgrenzung zur vEns

Die vEns wird weiterhin separat geführt:

```text
data/01_mapping/performing_ru_vens_mapping.csv
```

Diese Datei benötigt eine belastbare fachliche Quelle mit Gültigkeitszeitraum. Der öffentliche MP-ID-Import befüllt sie bewusst nicht automatisch.
