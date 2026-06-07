# Netzentgelt MVP – Phase 5A: kontrollierte manuelle Overrides

## Ziel

Die Erweiterung ergänzt eine auditierbare Bearbeitungsoberfläche für operative Prüffälle. Originaldateien aus `data/00_raw` werden niemals überschrieben. Bestätigte Korrekturen werden separat unter `data/01_mapping/manual_overrides.csv` gespeichert und bei jedem sicheren Pipeline-Neuaufbau auf die temporär importierten DuckDB-Rohdaten angewandt.

## Unterstützte Korrekturen

- Nutzendes EVU ergänzen oder korrigieren (`SET_PERFORMING_RU`)
- Loknummer ergänzen oder korrigieren (`SET_LOCO_NO`)
- Grenzzeitanker korrigieren (`SET_SEQUENCE_TS`)
- Abfahrtszeit korrigieren (`SET_ACTUAL_DEPARTURE`)
- Ankunftszeit korrigieren (`SET_ACTUAL_ARRIVAL`)
- Unterbrechung fachlich klassifizieren (`CLASSIFY_GAP`)
- Bearbeitungsnotiz hinterlegen (`CASE_NOTE`)

## Bewusste Grenze der Phase 5A

Klassifikationen wie „mögliche kalte Abstellung“ werden bereits nachvollziehbar gespeichert, verändern das Export-Gate aber noch **nicht** automatisch. Die dafür notwendigen Grenzwerte müssen zuerst fachlich verbindlich festgelegt werden.

## Neue Dateien im Projekt

- `scripts/manual_override_module.py`
- `scripts/manual_override_ui_module.py`
- `data/01_mapping/manual_overrides.csv` – wird beim ersten App- oder Pipeline-Lauf automatisch angelegt
- `data/01_mapping/manual_override_change_log.csv` – entsteht bei der ersten UI-Änderung

## Neue Audit-Exporte

Nach dem Pipeline-Lauf entstehen unter `data/03_exports`:

- `cfg_manual_overrides.csv`
- `cfg_manual_overrides_effective.csv`
- `dq_manual_override_conflicts.csv`
- `audit_manual_override_application.csv`

## Bedienung

Die Streamlit-App erhält den neuen Reiter **„3. Fall bearbeiten“**. Dort können offene Findings oder GAPs ausgewählt werden. Das Tool zeigt einen nachvollziehbaren Systemvorschlag, sofern eine belastbare Ableitung möglich ist. Jede gespeicherte Korrektur benötigt einen Kommentar und einen Bearbeiter.

Widersprüchliche aktive Overrides brechen die Pipeline verständlich ab. Sie werden niemals stillschweigend priorisiert.

## Installationsreihenfolge

```powershell
cd C:\00_Projects\LTE-individuelles-netzentgelt

.\01_DRY_RUN_MANUAL_OVERRIDE_PHASE5A.bat
.\02_APPLY_MANUAL_OVERRIDE_PHASE5A.bat
.\03_VERIFY_MANUAL_OVERRIDE_PHASE5A.bat
.\04_RUN_PIPELINE_AND_VERIFY_MANUAL_OVERRIDE_PHASE5A.bat
```

## Rollback

```powershell
.\05_ROLLBACK_MANUAL_OVERRIDE_PHASE5A.bat
```

Der Rollback stellt die geänderten Code-Dateien wieder her. Falls bereits ein produktiver Pipeline-Lauf gestartet wurde, werden zusätzlich der zuvor gesicherte DuckDB-Stand und der vollständige Exportordner restauriert.

`data/01_mapping/manual_overrides.csv` wird bewusst nicht gelöscht. Die fachlichen Entscheidungen bleiben als Audit Trail erhalten und können in der Oberfläche deaktiviert werden.
