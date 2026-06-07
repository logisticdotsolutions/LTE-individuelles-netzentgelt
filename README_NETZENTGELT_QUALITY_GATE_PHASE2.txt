NETZENTGELT MVP - PHASE 2: ZEITDECKUNG, EXPORT-GATE UND BETRIEBSAMPEL
===================================================================

Stand
-----
Dieses Paket baut additiv auf dem bereits eingespielten Hardening-Paket auf.
Es wurde für den aktuellen GitHub-main-Stand logisticdotsolutions/LTE-individuelles-netzentgelt
vom 07.06.2026 erstellt.

Ziel
----
Die bestehende Lok-Zeitachse wird um eine auditierbare Kontrollschicht ergänzt.
Die Kontrollschicht bewertet Lok-Tage 15-minutenscharf und verhindert dynamische
XLSX-Exporte, wenn blockierende Fehler bestehen.

Neue Tabellen
-------------
core_loco_day_coverage.csv
    Rechnerische Zeitdeckung je Lok und Kalendertag.

dq_export_gate.csv
    Export-Gate je Lok und Kalendertag: READY / WARNING / BLOCKED.

dq_export_gate_ru.csv
    Export-Gate je Lok, Kalendertag und PerformingRU.

dq_global_export_blockers.csv
    Globale Blocker, insbesondere R012 ohne eindeutig zuordenbare Lok.

export_excluded_rows.csv
    Auditliste der Bewegungen, die bewusst nicht exportiert wurden.

dq_reconciliation.csv
    Mengenabgleich von Rohdaten, Staging, Timeline, Findings und Exporten.

dq_operational_kpis.csv
    KPI-Liste für die Streamlit-Betriebsampel.

Fachliche Logik
---------------
- Berechnung erfolgt in 15-Minuten-Slots.
- Eine GAP-Zeile beendet ein Nutzungssegment.
- Ein Wechsel der PerformingRU beendet ein Nutzungssegment.
- ERROR und MANUAL_REVIEW blockieren den Export.
- Überschneidungsminuten blockieren den Export.
- Relevante GAPs über 8 Stunden blockieren den Export.
- Kurze relevante GAPs bleiben WARNING und werden sichtbar ausgewiesen.
- Nicht exportfähige Movements blockieren den betroffenen Lok-Tag.
- R012-Fälle ohne eindeutig zuordenbare Lok werden als globale Blocker behandelt.
- CSV- und XLSX-Exporte werden über dasselbe Gate geschützt.

Wichtige Abgrenzung
-------------------
Die Deckungsquote ist eine MVP-Kontrollschicht auf Basis der aus RailCube
ableitbaren Nutzungssegmente. Sie ersetzt noch nicht die vollständige AS4-/XML-
Marktkommunikation, Quittungen, Stornos oder Zuordnung-Meldetag-Nachrichten.

Dateien des Pakets
------------------
apply_netzentgelt_quality_gate_phase2.py
rollback_netzentgelt_quality_gate_phase2.py
validate_netzentgelt_quality_gate_phase2.py
payload/quality_gate_module.py
01_DRY_RUN_PHASE2.bat
02_APPLY_PHASE2.bat
03_RUN_FULL_IMPORT_AND_PIPELINE_PHASE2.bat
04_VALIDATE_PHASE2.bat
05_ROLLBACK_PHASE2.bat

Anwendung
---------
1. Sämtliche Dateien und den Ordner payload in den Projektstamm kopieren:

   C:\00_Projects\LTE-individuelles-netzentgelt

2. PowerShell im Projektstamm öffnen.

3. Trockenlauf ausführen:

   .\01_DRY_RUN_PHASE2.bat

4. Patch anwenden:

   .\02_APPLY_PHASE2.bat

5. Rohdaten neu laden, Pipeline berechnen und Tabellen validieren:

   .\03_RUN_FULL_IMPORT_AND_PIPELINE_PHASE2.bat

6. Streamlit starten:

   .venv\Scripts\python.exe -m streamlit run app\app.py

7. Git-Änderungen prüfen:

   git status

8. Nach erfolgreichem Test nur die produktiven Dateien committen:

   git add scripts\run_all.py scripts\export_module.py scripts\quality_gate_module.py app\app.py
   git commit -m "Add loco-day coverage, export gate and operational KPIs"
   git push

Nicht committen
---------------
.patch_backups\
.quality_gate_phase2_last_backup.txt
apply_netzentgelt_quality_gate_phase2.py
rollback_netzentgelt_quality_gate_phase2.py
validate_netzentgelt_quality_gate_phase2.py
01_DRY_RUN_PHASE2.bat
02_APPLY_PHASE2.bat
03_RUN_FULL_IMPORT_AND_PIPELINE_PHASE2.bat
04_VALIDATE_PHASE2.bat
05_ROLLBACK_PHASE2.bat
payload\

Validierung ohne neuen Import
-----------------------------
Wenn die Pipeline bereits erfolgreich gelaufen ist:

   .\04_VALIDATE_PHASE2.bat

Rollback
--------
Bei Problemen:

   .\05_ROLLBACK_PHASE2.bat

Danach Git-Status prüfen:

   git status

Erwartete UI-Erweiterung
------------------------
Im Überblick erscheint zusätzlich der Abschnitt:

   Betriebsampel & Export-Gate

Angezeigt werden:
- Lok-Tage READY
- Lok-Tage WARNING
- Lok-Tage BLOCKED
- Globale Blocker
- ausgeschlossene Exportzeilen
- operative KPI-Tabelle
- Reconciliation des letzten Pipeline-Laufs

Technische Tests des Pakets
---------------------------
- Python-Syntaxprüfung aller Patch- und Payload-Dateien erfolgreich.
- Dry-Run, Apply und Rollback gegen eine realitätsnahe Fixture erfolgreich.
- SQL-Logik gegen eine synthetische DuckDB erfolgreich geprüft:
  - Lok-Tag mit kurzer GAP-Zeit -> WARNING
  - Lok-Tag mit Überschneidung -> BLOCKED

VERSION 1.1
-----------
Der Patch unterstützt sowohl Windows-CRLF- als auch LF-Zeilenumbrüche und
schreibt die geänderten Dateien wieder im ursprünglichen Zeilenumbruchformat.
