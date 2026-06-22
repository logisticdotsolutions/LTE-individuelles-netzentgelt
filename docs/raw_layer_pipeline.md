# Raw-Layer-Pipeline

## Zweck

Der bisherige Tageslauf bleibt bestehen. Zusaetzlich gibt es jetzt eine zweite Pipeline-Variante mit stabiler Importbasis.

## Neue Dateien

- `scripts/pipeline/raw_import.py`
- `scripts/pipeline/full_rebuild_from_raw.py`
- `RUN_RAW_IMPORT.bat`

## Neue Datenbank

- `data/02_duckdb/netzentgelt_raw.duckdb`

## Neue Modi

```powershell
.\.venv\Scripts\python.exe scripts\run_pipeline.py --mode RAW_IMPORT_REBUILD
.\.venv\Scripts\python.exe scripts\run_pipeline.py --mode FULL_REBUILD_FROM_RAW
```

## Zielablauf

1. Raw-Import aus den CSV-Dateien:

```powershell
.\RUN_RAW_IMPORT.bat
```

2. Fachlicher Neuaufbau aus der Raw-DuckDB:

```powershell
.\.venv\Scripts\python.exe scripts\run_pipeline.py --mode FULL_REBUILD_FROM_RAW
```

## Nutzen

- CSV-Import ist vom fachlichen Rebuild getrennt.
- Korrekturen koennen spaeter aus einer stabilen Raw-Basis neu angewendet werden.
- Rohdatennahe Overrides wie Loknummer, Performing RU oder Zeiten koennen korrekt neu aufgebaut werden, ohne jedes Mal alle CSV-Dateien neu einzulesen.

## Naechster Schritt

Nach erfolgreichem lokalen Test wird der UI-Hintergrundlauf von `OVERRIDE_REBUILD` auf `FULL_REBUILD_FROM_RAW` umgestellt. Dadurch kann auch ein uebernommener Systemvorschlag mit rohdatennaher Wirkung schneller und sauberer neu gerechnet werden.
