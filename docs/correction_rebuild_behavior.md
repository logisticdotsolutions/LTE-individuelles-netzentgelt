# Korrektur- und Systemvorschlagsverhalten

## Ziel

Das Markieren eines Systemvorschlags in der UI darf keine Tagesberechnung ausloesen. Eine Neuberechnung startet nur dann, wenn eine Korrektur gespeichert und bewusst mit neu pruefen bestaetigt wird.

## Aktuelles Verhalten

- Checkbox in der Vorschlagsliste: nur UI-Auswahl, keine Pipeline-Berechnung.
- Ausgewaehlte Vorschlaege speichern: schreibt nur `manual_overrides.csv`, startet keine Berechnung.
- Speichern und neu pruefen: startet den schnellen Korrektur-Refresh.
- Der Korrektur-Refresh nutzt `CORRECTION_REBUILD`.
- `CORRECTION_REBUILD` fuehrt auf `scripts/pipeline/ui_refresh.py`.
- Die DuckDB wird aktualisiert, CSV-Dateien werden dabei nicht geschrieben.

## Rebuild-Modi

- `FULL_IMPORT_REBUILD`: vollstaendiger Legacy-Lauf ueber `run_all.py`.
- `RAW_IMPORT_REBUILD`: Rohdaten in `netzentgelt_raw.duckdb` importieren.
- `FULL_REBUILD_FROM_RAW`: Neuaufbau aus Raw-DuckDB inklusive CSV-Ausgaben.
- `CORRECTION_REBUILD`: schneller Korrektur-Refresh aus Raw-DuckDB ohne CSV-Ausgaben.
- `EXPORT_REBUILD`: Exporttabellen und CSV-Ausgaben aus vorhandener DuckDB neu schreiben.
- `OVERRIDE_REBUILD`: Legacy-Alias auf den schnellen Korrektur-Refresh, damit alte Aufrufe nicht brechen.

## Relevante Startpunkte

```powershell
git pull
.\RUN_TESTS.bat
.\RUN_TOOL.bat
.\RUN_CORRECTION_REBUILD.bat
.\.venv\Scripts\python.exe scripts\run_pipeline.py --mode CORRECTION_REBUILD
.\.venv\Scripts\python.exe scripts\run_pipeline.py --mode EXPORT_REBUILD
```
