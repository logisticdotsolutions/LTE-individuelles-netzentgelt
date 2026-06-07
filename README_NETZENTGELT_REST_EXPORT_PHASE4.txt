NETZENTGELT MVP - PHASE 4: LTE DE, LTE NL UND REST
=================================================

Ziel
----
Die Exportoberfläche wird auf drei fachlich verständliche Gruppen reduziert:
1. LTE DE
2. LTE NL
3. Rest

Rest umfasst sämtliche PerformingRUs außerhalb LTE DE und LTE NL.

Warum bleibt der Rest-Download je RU getrennt?
----------------------------------------------
Die offizielle XLSX-Vorlage enthält Marktpartner-Kopfdaten. Eine kombinierte
Rest-Datei mit mehreren PerformingRUs wäre deshalb fachlich mehrdeutig.
Die Oberfläche zeigt Rest gesammelt, der Download bleibt aber bewusst je
PerformingRU auswählbar.

Restübersicht
-------------
Die Restübersicht zeigt je PerformingRU:
- Betroffene Bewegungszeilen
- Davon exportfähig
- Davon gesperrt
- Betroffene Loks
- Betroffene Transporte

Zusätzlich wird OrderOwner angezeigt, sofern das Feld in den importierten Daten
verfügbar ist. Die Detailübersicht kann als CSV heruntergeladen werden.

Technische Änderung
-------------------
Geändert werden ausschließlich:
- app/app.py
- scripts/rest_export_module.py

Bestehende Pipeline- und Exportlogik bleibt unverändert.

Reihenfolge
-----------
01_DRY_RUN_REST_EXPORT_PHASE4.bat
02_APPLY_REST_EXPORT_PHASE4.bat
03_VALIDATE_REST_EXPORT_PHASE4.bat
04_RUN_STREAMLIT_REST_EXPORT_PHASE4.bat

Rollback
--------
05_ROLLBACK_REST_EXPORT_PHASE4.bat

Commit
------
06_GIT_COMMIT_REST_EXPORT_PHASE4.bat
git push
