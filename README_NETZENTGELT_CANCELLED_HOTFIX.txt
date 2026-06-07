NETZENTGELT MVP - CANCELLED FILTER HOTFIX PHASE 5 v1.1
=================================================

Zweck
-----
Stornierte Transporte mit TransportStatus = Cancelled beziehungsweise Canceled
werden fachlich ausgeschlossen.

Sie bleiben als Rohdaten erhalten und werden zusätzlich auditierbar dokumentiert,
aber nicht mehr in Timeline, Fehlerqueue, Quality Gate oder Exporte übernommen.

Geänderte Dateien
-----------------
scripts/run_all.py
scripts/error_rules.py
scripts/export_module.py
app/app.py

Neue Audit-Ausgabe
------------------
data/03_exports/audit_excluded_cancelled_transports.csv

Reihenfolge
-----------
1. 01_DRY_RUN_CANCELLED_HOTFIX.bat
2. 02_APPLY_CANCELLED_HOTFIX.bat
3. 03_RUN_FULL_IMPORT_AND_PIPELINE_CANCELLED_HOTFIX.bat
4. 04_VALIDATE_CANCELLED_HOTFIX.bat
5. Streamlit normal starten und fachlich prüfen
6. 06_GIT_COMMIT_CANCELLED_HOTFIX.bat
7. git push

Rollback
--------
05_ROLLBACK_CANCELLED_HOTFIX.bat


Version 1.1
-----------
- Doppelt vorkommende relevante_loco-Passage robust behandelt.
- Cancelled-Transporte zusätzlich zentral über TransportNumber ausgeschlossen.
- Der Ausschluss greift damit auch, wenn LocomotiveMovement.csv kein
  TransportStatus-Feld enthält.
- Die unscharfe Fallback-Spalte Status wird nicht mehr verwendet.
