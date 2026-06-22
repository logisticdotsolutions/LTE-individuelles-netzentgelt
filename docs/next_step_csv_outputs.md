# Naechster Schritt: CSV-Ausgaben aus run_all.py delegieren

Mit `scripts/pipeline/csv_outputs.py` ist die zentrale CSV-Ausgabe-Liste vorbereitet.

Der naechste lokale Patch an `scripts/run_all.py` soll nur drei Dinge tun:

1. Import ergaenzen: `from pipeline.csv_outputs import export_all_csv_outputs`
2. Den bisherigen langen Export-Loop am Ende des Tageslaufs entfernen.
3. Stattdessen `export_all_csv_outputs(con, EXP_DIR)` aufrufen.

Der fachliche Output darf sich dadurch nicht veraendern. Dateinamen, Tabellenreihenfolge, Trennzeichen und Header-Option bleiben durch das neue Modul gleich.

## Validierung

Nach dem lokalen Patch ausfuehren:

```powershell
git pull
.\RUN_TESTS.bat
.\RUN_TOOL.bat
.\.venv\Scripts\python.exe scripts\run_pipeline.py
```

## Erwarteter Nutzen

- `run_all.py` wird kleiner.
- Der Exportblock ist separat testbar.
- `EXPORT_REBUILD` kann danach gezielt implementiert werden.
- Spaetere Aenderungen an Exportdateien muessen nicht mehr im Monolithen gesucht werden.
