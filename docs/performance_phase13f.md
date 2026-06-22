# Performance Phase 13F/13G

## Ziel

Die Korrekturmaske soll sich beim Markieren von Systemvorschlaegen deutlich schneller anfuehlen. Insbesondere darf ein Checkbox-Rerun nicht jedes Mal die komplette Vorschlagslogik neu aufbauen.

## Umgesetzt

### 1. Session-Cache fuer Systemvorschlaege

Neue Runtime:

```text
scripts/manual_override_suggestion_cache_runtime_module.py
```

Wirkung:

- `manual_override_ui_module.build_suggestion_table` wird zur Laufzeit gepatcht.
- Die Vorschlagsliste wird im Streamlit-Session-State gecacht.
- Der Cache wird invalidiert, wenn sich die produktive DuckDB-Datei oder der sichtbare Finding-/Timeline-Kontext aendert.
- Checkbox-Reruns im Data Editor verwenden den vorhandenen Vorschlags-Cache.

Erwartung:

- Erstes Laden der Vorschlaege: unveraendert, weil echte Berechnung.
- Danach Haken setzen/entfernen: deutlich schneller.

### 2. CORRECTION_REBUILD-Modus

Neue Pipeline:

```text
scripts/pipeline/correction_rebuild.py
```

Wirkung:

- Wenn `netzentgelt_raw.duckdb` fehlt, wird zuerst `RAW_IMPORT_REBUILD` ausgefuehrt.
- Danach wird `FULL_REBUILD_FROM_RAW` ausgefuehrt.
- Wenn Raw bereits vorhanden ist, wird direkt aus Raw neu gerechnet.

CLI-Test:

```powershell
.\.venv\Scripts\python.exe scripts\run_pipeline.py --mode CORRECTION_REBUILD
```

## Wichtig

Die direkte Umstellung der Async-UI-Defaultschaltung von `OVERRIDE_REBUILD` auf `CORRECTION_REBUILD` ist vorbereitet, aber der direkte Patch in `app/secure_app.py` wurde beim Schreiben durch den Connector blockiert.

Der Performance-Fix fuer das Haken/Checkbox-Verhalten ist trotzdem aktiv, weil `install_suggestion_cache_runtime()` bereits in `secure_app.py` eingebunden ist.

## Lokal testen

```powershell
git pull
.\RUN_TESTS.bat
.\RUN_TOOL.bat
```

Testfall UI:

1. In Systemvorschlaege wechseln.
2. Warten, bis Vorschlaege initial geladen sind.
3. Mehrere Haken setzen/entfernen.
4. Die Seite darf dabei nicht jedes Mal mehrere Sekunden haengen.

Testfall Pipeline:

```powershell
.\.venv\Scripts\python.exe scripts\run_pipeline.py --mode CORRECTION_REBUILD
```
