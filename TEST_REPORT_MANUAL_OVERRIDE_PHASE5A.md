# Test Report – Netzentgelt MVP Phase 5A

## Geprüfter GitHub-Stand

Unmittelbar vor der Paketerstellung wurden die betroffenen Dateien über den GitHub-Connector geprüft:

- `scripts/run_all.py`: GitHub Blob `24b97a49f1dacb2418526e96e676a59cabeae293`
- `app/app.py`: GitHub Blob `05e36343889852d71a0cb4c451c0703610d358a2`

Der bereits umgesetzte zentrale Cancelled-/Canceled-Ausschluss ist in diesem Stand enthalten und bleibt unverändert.

## Paket-Selbsttest

Erfolgreich geprüft:

- Dry-Run ohne Dateiveränderung
- abschnittsspezifische und eindeutige Patch-Anker
- Apply mit automatischem Backup
- Python-Syntaxprüfung
- Windows-CRLF-Erhalt
- bytegenauer Code-Rollback
- Entfernen neu angelegter Module beim Rollback
- sicherer Abbruch bei absichtlich mehrdeutigem Anker

## Fachlicher DuckDB-Smoke-Test

Erfolgreich geprüft:

- `SET_LOCO_NO` aktualisiert `raw_locomotivemovement` und `raw_transportdetail`
- `SET_PERFORMING_RU` aktualisiert die temporär importierten Bewegungsdaten
- `SET_ACTUAL_DEPARTURE` aktualisiert die temporär importierten Bewegungsdaten
- `SET_SEQUENCE_TS` aktualisiert den Staging-Zeitanker mit Quelle `MANUAL_OVERRIDE`
- `CLASSIFY_GAP` wird dokumentiert, verändert aber in Phase 5A kein Export-Gate
- jede Anwendung wird in `audit_manual_override_application` protokolliert
- widersprüchliche aktive Overrides stoppen die Pipeline

## Runtime-Sicherung

Erfolgreich geprüft:

- Sicherung des bestehenden DuckDB-Standes
- Sicherung des vollständigen Exportordners
- Restaurierung des DuckDB-Standes
- Restaurierung des vollständigen Exportordners
