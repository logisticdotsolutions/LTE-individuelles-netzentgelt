# Test Report – Netzentgelt Cancelled-Hotfix V2

## Geprüfter GitHub-Stand

Repository: `logisticdotsolutions/LTE-individuelles-netzentgelt`  
Branch: `main`  
Beim Abruf geprüfte Dateien:

- `scripts/run_all.py`
- `scripts/error_rules.py`
- `scripts/export_module.py`
- `scripts/quality_gate_module.py`
- `scripts/rest_export_module.py`
- `app/app.py`

## Umgesetzte Fachlogik

- Zentraler Ausschluss über `TransportNumber`
- Statusquelle: `TransportDetail.csv`
- Akzeptierte Statuswerte: `Cancelled`, `Canceled`
- Ausschluss aus Timeline-Staging
- Ausschluss aus Routenerkennung
- Ausschluss aus R012 für beide Rohdatenquellen
- Downstream-Ausschluss aus Quality Gate, Rest-Export und XLSX-Exporten über die bereinigte Timeline
- Audit-Tabelle und Audit-CSV
- Ergänzende Auditfelder aus `LocomotiveMovement.csv`:
  - `TransportLastEditDate`
  - `TransportLastEditBy`

## Automatisierte Tests

Erfolgreich ausgeführt:

1. Installer-Selbsttest
   - Dry-Run ohne Dateiveränderung
   - Apply
   - Python-Syntaxprüfung
   - CRLF-Erhalt
   - bytegenauer Rollback

2. Ende-zu-Ende-Snapshot-Test
   - CRLF-Projektdateien
   - Apply gegen funktionsabschnittsspezifische Anker
   - DuckDB-Smoke-Test
   - `Cancelled` und `Canceled`
   - statuslose `LocomotiveMovement.csv`
   - Ausschluss aus Timeline-Staging
   - Ausschluss aus Routenerkennung
   - kein R012 für stornierte Transporte
   - R012 bleibt für aktive Vergleichsfälle wirksam
   - Audit enthält `TransportLastEditDate` und `TransportLastEditBy`
   - Rollback

3. Runtime-Backup und Runtime-Rollback
   - Sicherung der produktiven DuckDB
   - Sicherung des vollständigen Exportordners
   - Wiederherstellung des alten Datenstands
   - Entfernung neu entstandener Exportdateien bei Rollback

4. Produktionsprüfungsmodus des Verifiers
   - zentrale Ausschlusstabelle vorhanden
   - Audittabelle vorhanden
   - Audit-CSV vollständig strukturiert
   - keine ausgeschlossenen Transporte in:
     - `stg_loco_events`
     - `core_loco_timeline`
     - `stg_transport_details_enriched`
     - `core_transport_route`
     - `dq_findings`

## Bewusst nicht verändert

- `scripts/quality_gate_module.py`
- `scripts/rest_export_module.py`

Begründung: Beide Module arbeiten downstream auf der bereinigten Timeline. Eine zusätzliche parallele Filterlogik würde die Wartbarkeit verschlechtern und könnte divergierende Regeln erzeugen.
