# Bahnstrom Deutschland – Tagesprüfung

Lokale Streamlit-Fachanwendung zur operativen Prüfung und Exportvorbereitung für das individuelle Netzentgelt in Deutschland.

## Zweck

Das Tool verarbeitet die aktuellen Rohdaten, baut die DuckDB-Datenbasis reproduzierbar neu auf und unterstützt Fachanwender bei der Prüfung auffälliger Lok-Zeitachsen. Korrekturen werden lokal, nachvollziehbar und auditierbar dokumentiert. Die importierten Original-CSVs bleiben unverändert.

## Normaler Start

Im Repository-Stamm ausführen:

```bat
RUN_TOOL.bat
```

Die Anwendung startet über `app/secure_app.py`. Die lokale Anmeldung, Rollensteuerung und Auditzuordnung werden vor der eigentlichen Fachanwendung aktiviert.

## Testsuite

Vor und nach Änderungen ausführen:

```bat
RUN_TESTS.bat
```

Die Testsuite prüft:

- Python-Syntax
- Test-Abhängigkeiten
- Regelengine und Quality Gate
- Exportlogik
- lokale Korrekturen und Audit Trail
- Rollen- und UI-Runtime-Bridges
- Cleanup-Verträge für entfernte historische Artefakte

Testberichte werden unter `_test_reports/<UTC-Zeitstempel>/` abgelegt.

## Operativer Ablauf

1. Daten aktualisieren und vollständig neu berechnen.
2. Blockierende Fälle unter **2. Offene Aufgaben** prüfen.
3. Lok-Kontext mit Zeitachse, Grenzübertritten und GAPs öffnen.
4. Notwendige lokale Korrektur oder fachliche Klassifikation dokumentieren.
5. Export erst nach erfolgreicher Prüfung erstellen.

## Zentrale Verzeichnisse

```text
data/00_raw       Eingangsdaten als CSV
data/01_mapping   fachliche Mappings und lokale Overrides
data/02_duckdb    produktive und temporäre DuckDB-Dateien
data/03_exports   erzeugte CSV-Prüf- und Exportdaten
data/04_logs      technische Laufprotokolle
scripts/          produktive Python-Module
tests/            automatisierte Regressionstests
```

## Sicherheitsprinzipien

- Der Neuaufbau erfolgt zuerst in einer temporären DuckDB-Datei.
- Die produktive DuckDB wird nur nach einem vollständig erfolgreichen Lauf ersetzt.
- Lokale Korrekturen verändern keine importierten Original-CSVs.
- Deaktivierungen von Korrekturen erzeugen je Override einen eigenen Audit-Eintrag.
- Pipeline-Aktionen sind nur für ADMIN sichtbar.

## Wartung

Historische Patch-Installer und reine Installer-Roundtrip-Tests gehören nicht mehr zum produktiven Repository. Neue Änderungen werden direkt auf Basis von `main` entwickelt und durch `RUN_TESTS.bat` abgesichert.
