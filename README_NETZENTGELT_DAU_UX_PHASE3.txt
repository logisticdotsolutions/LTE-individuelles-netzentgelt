NETZENTGELT MVP - PHASE 3: DAU-TAUGLICHE OPERATOR UI
====================================================

VORAUSSETZUNG
-------------
Phase 2 v1.1 muss zuerst vollstaendig angewendet worden sein:
- 01_DRY_RUN_PHASE2.bat
- 02_APPLY_PHASE2.bat
- 03_RUN_FULL_IMPORT_AND_PIPELINE_PHASE2.bat
- 04_VALIDATE_PHASE2.bat

ZIEL DER PHASE 3
----------------
Die fachliche Berechnung wird nicht veraendert. Die Oberflaeche wird fuer
gelegentliche Fachanwender selbsterklaerend aufgebaut.

NEU IN DER OBERFLAECHE
----------------------
1. Tagespruefung
   - klare Aussage: Export moeglich oder gesperrt
   - Freigegebene Lok-Tage
   - Lok-Tage mit Hinweis
   - Gesperrte Lok-Tage
   - Globale Export-Sperren
   - gefuehrter Ablauf
   - Klartext-Erklaerung fuer gesperrte Lok-Tage

2. Offene Aufgaben
   - gesperrte Lok-Tage
   - globale Export-Sperren
   - Hinweise
   - technische Einzelprueffaelle
   - klare naechste Schritte
   - CSV-Download der Arbeitsliste
   - Loknummer fuer Detailpruefung vormerken

3. Lok pruefen
   - bisherige Timeline bleibt erhalten
   - Begriffe werden eindeutiger und deutschsprachig dargestellt

4. Exporte erstellen
   - bestehende Exportlogik bleibt erhalten
   - Phase 2 blockiert Exporte bei offenen Sperrfaellen

Technische Tabs bleiben bewusst erhalten, sind aber klar als Technik-Bereiche
gekennzeichnet.

GEAENDERTE DATEIEN
------------------
- app/app.py
- scripts/operator_ui_module.py  (neu)

AUSFUEHRUNG
-----------
1. 01_DRY_RUN_DAU_UX_PHASE3.bat
2. 02_APPLY_DAU_UX_PHASE3.bat
3. 03_VALIDATE_DAU_UX_PHASE3.bat
4. 04_RUN_STREAMLIT_DAU_UX_PHASE3.bat

NACH DEM TEST
-------------
5. 06_GIT_COMMIT_DAU_UX_PHASE3.bat
6. git push

ROLLBACK
--------
05_ROLLBACK_DAU_UX_PHASE3.bat

BACKUP
------
Das Patch-Skript legt vor der Aenderung automatisch ein Backup an:
.patch_backups\netzentgelt_dau_ux_phase3_YYYYMMDD_HHMMSS
