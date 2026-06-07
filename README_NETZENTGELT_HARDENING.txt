NETZENTGELT MVP - VOLLUMFÄNGLICHES HARDENING-PAKET
===================================================
Patch-ID: NETZENTGELT_HARDENING_V1_20260607

ZWECK
-----
Dieses Paket baut auf dem aktuellen GitHub-Stand auf und behebt die bei der
Codeprüfung gefundenen Inkonsistenzen. Es ändert ausschließlich:

- scripts/download_blob_data.py
- scripts/run_all.py
- scripts/error_rules.py
- scripts/export_module.py
- app/app.py

UMGESETZTE ANPASSUNGEN
----------------------
1. Einheitlicher Snapshot-Zeitpunkt
   - download_blob_data.py schreibt nach erfolgreichem Gesamtdownload
     data/00_raw/raw_import_manifest.json.
   - App, Pipeline und Fehlerregeln verwenden denselben stabilen Snapshot.
   - Ein erneuter run_all.py-Lauf ohne neuen Download verschiebt den 24h-Cutoff
     nicht mehr.

2. Gesamthafter Rohdaten-Download
   - Dateien werden zuerst temporär geladen und validiert.
   - Erst nach erfolgreicher Verarbeitung aller Dateien werden sie übernommen.
   - Scheitert das Ersetzen einer Datei, wird auf den vorherigen lokalen Stand
     zurückgerollt.

3. Fail-Fast für Pflichtimporte
   - run_all.py bricht ab, wenn LocomotiveMovement.csv, TransportDetail.csv oder
     Locomotive.csv nicht vollständig importiert werden konnten.

4. Halter-Ableitung korrigiert
   - ANE_TENS / Marktpartner-ID des Halters wird anhand holder_name bzw.
     Lok-Halter aufgelöst und nicht mehr anhand PerformingRU.

5. CSV- und XLSX-Export konsolidiert
   - run_all.py verwendet nur noch die zentrale Exportlogik aus export_module.py.
   - Die bisherigen Fallbacks bleiben erhalten:
       Nutzer-vEns = PerformingRU, falls kein Mapping vorhanden
       Halter-MP-ID = Haltername, falls kein Mapping vorhanden
       Meldungstyp = leer

6. Export-Blocking
   - Nach der Finding-Berechnung wird export_ready neu aufgebaut.
   - Offene ERROR- und MANUAL_REVIEW-Findings blockieren betroffene Bewegungen.
   - Dynamische Nutzungsmeldungssegmente mit blockierenden Bewegungen werden
     nicht exportiert.
   - Aufenthaltsereignisse mit aktivem Manual-Review-Flag werden nicht exportiert.

7. Audit Trail
   - dq_run_metadata wird erzeugt und als CSV exportiert.
   - Enthalten sind Snapshot-Zeitpunkt, 24h-Cutoff und Berechnungszeitpunkt.

8. UI-Diagnose vereinheitlicht
   - Bei LocomotiveMovement wird für die 24h-Prüfung ActualDeparture verwendet;
     falls dieses fehlt, dient ActualArrival als Fallback.

ANWENDUNG
---------
1. ZIP entpacken.
2. Sämtliche Dateien aus diesem Paket in den STAMMORDNER des lokalen Repositories
   kopieren, also beispielsweise:

   C:\00_Projects\LTE-individuelles-netzentgelt

3. 01_DRY_RUN.bat ausführen.
   Erst fortfahren, wenn der Trockenlauf erfolgreich abgeschlossen wurde.

4. 02_APPLY_PATCH.bat ausführen.
   Das Skript legt automatisch Backups an:

   .patch_backups\netzentgelt_hardening_YYYYMMDD_HHMMSS

5. 03_RUN_FULL_IMPORT_AND_PIPELINE.bat ausführen.
   Dadurch werden aktuelle Blob-Daten geladen und die DuckDB vollständig neu
   berechnet.

6. Streamlit-Anwendung starten und folgende Bereiche kontrollieren:
   - Überblick: Letzter Import
   - Dummys & missing Locos
   - Fehlerqueue
   - XLSX-Nutzungsmeldung
   - XLSX-Aufenthaltsereignisse
   - data/03_exports/dq_run_metadata.csv

ROLLBACK
--------
Bei Problemen 04_ROLLBACK.bat ausführen. Dadurch werden die fünf Dateien aus dem
letzten automatisch angelegten Backup wiederhergestellt.

WICHTIG
-------
Das Paket verändert keine Rohdaten, keine Mapping-Dateien und keine Vorlagen.
Die produktive DuckDB wird weiterhin erst nach erfolgreichem Pipeline-Lauf durch
den neuen Build-Stand ersetzt.
