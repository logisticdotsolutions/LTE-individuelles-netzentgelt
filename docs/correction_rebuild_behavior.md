# Korrektur- und Systemvorschlagsverhalten

## Ziel

Das Markieren eines Systemvorschlags in der UI darf keine vollstaendige Tagesberechnung ausloesen. Eine Neuberechnung soll nur dann starten, wenn eine Korrektur tatsaechlich gespeichert und bewusst mit "neu pruefen" bestaetigt wird.

## Verhalten ab Phase 13C

- Checkbox in der Vorschlagsliste: nur UI-Auswahl, keine Pipeline-Berechnung.
- "Ausgewaehlte Vorschlaege speichern": schreibt nur `manual_overrides.csv`, startet keine Berechnung.
- "Speichern und neu pruefen": startet die Hintergrundberechnung.
- Die Hintergrundberechnung nutzt bevorzugt `OVERRIDE_REBUILD`, nicht mehr den kompletten `run_all.py`-Full-Run.

## Sicherheitsgrenze

`OVERRIDE_REBUILD` ist fuer schnelle Korrekturlaeufe gedacht. Wenn sich rohdatenaendernde Overrides geaendert haben, bricht der Modus ab und verlangt einen vollstaendigen Neuaufbau.

Rohdatenaendernde Override-Typen:

- `SET_LOCO_NO`
- `SET_PERFORMING_RU`
- `SET_ACTUAL_DEPARTURE`
- `SET_ACTUAL_ARRIVAL`

Das verhindert, dass bereits in der produktiven DuckDB angewandte Rohdatenkorrekturen unsichtbar fortgeschrieben werden.

## Relevante Startpunkte

```powershell
.\RUN_OVERRIDE_REBUILD.bat
.\RUN_EXPORT_REBUILD.bat
.\.venv\Scripts\python.exe scripts\run_pipeline.py --mode OVERRIDE_REBUILD
```
