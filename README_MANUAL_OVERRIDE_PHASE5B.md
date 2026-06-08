# Netzentgelt MVP – Phase 5B Systemvorschläge

## Ziel

Phase 5B ergänzt das in Phase 5A eingeführte Korrektur-Cockpit um eine regelbasierte Vorschlags-Engine. Die Engine reduziert den manuellen Suchaufwand, nimmt aber keine fachlichen Entscheidungen selbstständig vor.

**Sicherheitsprinzip:** Kein Vorschlag wird automatisch gespeichert, auf Rohdaten angewandt oder exportfreigebend bewertet. Eine verantwortliche Person muss den Vorschlag bewusst in die Bearbeitungsmaske übernehmen, fachlich prüfen, kommentieren und speichern.

## Geprüfter GitHub-Stand

Repository: `logisticdotsolutions/LTE-individuelles-netzentgelt`

Grundlage: `main` auf Commit:

```text
d276d8fb4b07382e1382d4ad9994f0fc636cbc1c
feat: add audited manual override cockpit
```

## Geänderte Dateien

```text
scripts/manual_override_ui_module.py
scripts/manual_override_suggestion_module.py   (neu)
```

Bewusst **nicht** verändert:

```text
scripts/run_all.py
scripts/error_rules.py
scripts/export_module.py
scripts/quality_gate_module.py
scripts/rest_export_module.py
app/app.py
```

## Vorschlagslogik

| Vorschlag | Sicherheitsstufe | Verhalten |
|---|---:|---|
| PerformingRU aus identischen vorherigen und nachfolgenden Bewegungen derselben Lok | HIGH | Wert wird zur bewussten Übernahme vorgeschlagen |
| PerformingRU aus eindeutiger Nachbarschaft | MEDIUM | Wert wird zur Prüfung vorgeschlagen |
| Widersprüchliche PerformingRUs | LOW | Keine Vorauswahl, nur Hinweis |
| Genau eine plausible Loknummer aus TransportDetail und LocomotiveMovement | HIGH | Loknummer wird vorgeschlagen |
| Genau eine plausible Loknummer aus nur einer Quelle | MEDIUM | Loknummer wird vorgeschlagen |
| Mehrere plausible Loknummern | LOW | Keine Vorauswahl, nur Hinweis |
| Grenzzeitanker aus bestehender Richtungslogik | MEDIUM | Zeitwert wird zur Prüfung vorgeschlagen |
| Grenzereignis außerhalb des Viertelstundenrasters | LOW | Gerundeter Viertelstundenwert wird ausschließlich als Prüfvorschlag angezeigt |
| Gebrochene Ortskette | MEDIUM | Klassifikation `MISSING_MOVEMENT` wird vorgeschlagen |
| Standzeit ab 480 Minuten am selben Ort | MEDIUM | Klassifikation `COLD_STAND` wird vorgeschlagen |

## Fachliche Grenze

GPS-Grenzpunktdaten sind aktuell nicht Bestandteil der Anwendung. Deshalb bleibt die Rundung von Grenzereignissen auf ein Viertelstundenraster ein LOW-Prüfvorschlag. Sie darf nicht automatisch übernommen werden.

Auch eine mögliche kalte Abstellung verändert das Quality Gate in Phase 5B noch nicht automatisch. Dafür müssen zuerst verbindliche fachliche Grenzwerte und zulässige Freigaberegeln beschlossen werden.

## Neue Bedienung

Im bestehenden Reiter:

```text
3. Fall bearbeiten
```

stehen nun vier Unterreiter zur Verfügung:

```text
Systemvorschläge
Neue Korrektur
Aktive Overrides
Audit und Hinweise
```

Vorgehen:

1. Unter `Systemvorschläge` Sicherheitsstufe und Vorschlagsart filtern.
2. Vorschlag auswählen.
3. `Vorschlag in Bearbeitungsmaske übernehmen` anklicken.
4. Unter `Neue Korrektur` Werte, Nachweis und Begründung fachlich kontrollieren.
5. Kommentar ergänzen.
6. Override speichern oder direkt speichern und neu prüfen.

## Audit Trail

Übernommene Vorschläge werden zusätzlich protokolliert:

```text
data/01_mapping/manual_override_suggestion_acceptance_log.csv
```

Die Datei enthält unter anderem:

```text
suggestion_id
override_id
suggestion_type
override_type
confidence
suggested_value
accepted_value
classification_code
transport_number
loco_no
period_start_utc
period_end_utc
accepted_by
reason
evidence
comment
```

Die bestehenden Audit-Dateien aus Phase 5A bleiben unverändert bestehen.

## Installation

Im Projektstamm ausführen:

```powershell
cd C:\00_Projects\LTE-individuelles-netzentgelt

Expand-Archive `
  -LiteralPath "$env:USERPROFILE\Downloads\Netzentgelt_Manual_Overrides_Phase5B.zip" `
  -DestinationPath . `
  -Force

.\01_DRY_RUN_MANUAL_OVERRIDE_PHASE5B.bat
.\02_APPLY_MANUAL_OVERRIDE_PHASE5B.bat
.\03_VERIFY_MANUAL_OVERRIDE_PHASE5B.bat
.\04_RUN_PHASE5B_LOGIC_TESTS.bat
```

Danach Anwendung starten:

```powershell
.venv\Scripts\python.exe -m streamlit run app\app.py
```

## Rollback

```powershell
.\05_ROLLBACK_MANUAL_OVERRIDE_PHASE5B.bat
```

Der Rollback stellt ausschließlich den Code-Stand vor Phase 5B wieder her. Fachlich erfasste operative Overrides und Audit-Protokolle werden bewusst nicht gelöscht.

## Git-Commit nach lokalem Test

```powershell
git status --short

git diff -- scripts/manual_override_ui_module.py

git add scripts/manual_override_ui_module.py
git add scripts/manual_override_suggestion_module.py

git commit -m "feat: add rule-based manual override suggestions"

git push
```

Operative Laufzeitdaten nicht committen:

```text
data/01_mapping/manual_overrides.csv
data/01_mapping/manual_override_change_log.csv
data/01_mapping/manual_override_suggestion_acceptance_log.csv
```
