# Netzentgelt MVP – Phase 5D

## Zweck

Phase 5D erweitert ausschließlich das bestehende Cockpit für manuelle Overrides und Systemvorschläge.

Neu:

1. Systemvorschläge können in der Liste per Checkmark ausgewählt und gesammelt gespeichert werden.
2. Für ein DE-relevantes GAP wird eine PerformingRU vorgeschlagen, wenn die unmittelbar vorherige und die unmittelbar nachfolgende Bewegung derselben Lok dieselbe PerformingRU enthalten.
3. Fachlich identische aktive Overrides werden nicht doppelt angelegt.

## Sicherheitsprinzip

- Kein Vorschlag wird automatisch gespeichert.
- Für eine Sammelübernahme müssen Vorschläge explizit per Checkmark markiert werden.
- Ein gemeinsamer Pflichtkommentar und ein Bearbeiter sind erforderlich.
- Die Rohdaten bleiben unverändert.
- RailCube wird nicht verändert.
- Die GAP-PerformingRU-Empfehlung wird als lokale, auditierbare Klassifikation gespeichert.
- Die GAP-PerformingRU-Empfehlung hebt keine Exportsperre automatisch auf.

## Geänderte Dateien

```text
scripts/manual_override_ui_module.py
scripts/manual_override_suggestion_module.py
scripts/manual_override_batch_module.py   # neu
```

Nicht verändert werden insbesondere:

```text
app/app.py
scripts/run_all.py
scripts/error_rules.py
scripts/export_module.py
scripts/quality_gate_module.py
scripts/rest_export_module.py
scripts/manual_override_module.py
scripts/operational_day_filter_module.py
```

## Installation

Im Projektstamm ausführen:

```powershell
cd C:\00_Projects\LTE-individuelles-netzentgelt

Expand-Archive `
  -LiteralPath "$env:USERPROFILE\Downloads\Netzentgelt_Manual_Override_Phase5D.zip" `
  -DestinationPath . `
  -Force

.\01_DRY_RUN_MANUAL_OVERRIDE_PHASE5D.bat
.\02_APPLY_MANUAL_OVERRIDE_PHASE5D.bat
.\03_VERIFY_MANUAL_OVERRIDE_PHASE5D.bat
.\04_RUN_MANUAL_OVERRIDE_PHASE5D_TESTS.bat
```

Danach die App starten:

```powershell
.venv\Scripts\python.exe -m streamlit run app\app.py
```

## Rollback

```powershell
.\05_ROLLBACK_MANUAL_OVERRIDE_PHASE5D.bat
```

## Erwartete Bedienung

Im Reiter `3. Fall bearbeiten` → `Systemvorschläge`:

1. Vorschläge anhand von Sicherheit, Begründung und Nachweis prüfen.
2. Gewünschte Zeilen links mit einem Checkmark markieren.
3. Bearbeiter und gemeinsamen Kommentar erfassen.
4. `Ausgewählte Vorschläge speichern` oder `Speichern und neu prüfen` auswählen.

Die bisherige detaillierte Einzelfallmaske bleibt weiterhin verfügbar.

## Git-Commit nach erfolgreichem lokalen Test

```powershell
git status --short

git diff -- scripts/manual_override_ui_module.py scripts/manual_override_suggestion_module.py

git add scripts/manual_override_ui_module.py
git add scripts/manual_override_suggestion_module.py
git add scripts/manual_override_batch_module.py

git commit -m "feat: add bulk suggestion acceptance and gap performing ru proposal"

git push
```

Operative CSV-Dateien, Backupordner und Installationsskripte nicht committen.
