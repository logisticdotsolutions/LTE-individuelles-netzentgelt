# Netzentgelt Cancelled-Hotfix V2

## Zweck

Transporte mit `TransportStatus = Cancelled` oder `TransportStatus = Canceled` werden fachlich zentral über ihre Transportnummer ausgeschlossen. Der Status wird aus `TransportDetail.csv` gelesen. Dadurch werden auch zugehörige Zeilen aus `LocomotiveMovement.csv` entfernt, obwohl diese Rohdatei selbst kein `TransportStatus` enthalten muss.

Der Hotfix verändert ausschließlich:

- `scripts/run_all.py`
- `scripts/error_rules.py`
- `scripts/export_module.py`
- `app/app.py`

`quality_gate_module.py` und `rest_export_module.py` benötigen keine direkte Änderung: Beide arbeiten downstream auf der bereits bereinigten Timeline.

## Wirkung

Stornierte Transporte werden nicht in das Lok-Staging, die Timeline, die Routenerkennung, R012-Findings, Quality Gates oder Exporte übernommen. Der Ausschluss wird in `data/03_exports/audit_excluded_cancelled_transports.csv` auditierbar dokumentiert.

Die Audit-Datei enthält:

- `source_table`
- `transport_number`
- `transport_status`
- `affected_rows`
- `first_seen_utc`
- `last_seen_utc`
- `transport_last_edit_date`
- `transport_last_edit_by`

`transport_last_edit_date` und `transport_last_edit_by` werden defensiv aus `LocomotiveMovement.csv` übernommen. Fehlen die Spalten in einem Rohdatenstand, bleiben die Werte leer; der Tageslauf wird dadurch nicht blockiert.

## Sicherheitsmechanismen

- Dry-Run vor Anwendung
- funktionsabschnittsspezifische und auf Eindeutigkeit geprüfte Suchstellen
- automatische Backups unter `.patch_backups/`
- automatische Rücksicherung, falls Apply oder Syntaxprüfung fehlschlägt
- expliziter Code-Rollback
- Runtime-Backup vor dem produktiven Tageslauf für DuckDB und `data/03_exports`
- Runtime-Rollback auf den letzten vor dem Tageslauf gesicherten Datenstand
- Python-Syntaxprüfung
- Erhalt vorhandener LF- oder Windows-CRLF-Zeilenumbrüche
- isolierter DuckDB-Smoke-Test
- produktive Prüfung nach dem Neuaufbau der DuckDB

## Reihenfolge

1. `01_DRY_RUN_CANCELLED_HOTFIX.bat`
2. `02_APPLY_CANCELLED_HOTFIX.bat`
3. `03_VERIFY_CANCELLED_HOTFIX.bat`
4. `04_RUN_PIPELINE_AND_VERIFY_CANCELLED_HOTFIX.bat`
5. Erst nach erfolgreichem lokalen Test selbst committen und pushen.

Bei Problemen:

- `05_ROLLBACK_CANCELLED_HOTFIX.bat`

Der Rollback stellt den Code aus dem letzten Apply-Backup wieder her. Wurde bereits der produktive Tageslauf über Skript 04 gestartet, werden zusätzlich die zuvor gesicherte DuckDB und der vollständige Exportordner wiederhergestellt.
