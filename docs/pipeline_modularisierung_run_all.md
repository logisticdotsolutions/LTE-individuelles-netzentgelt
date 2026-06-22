# Modularisierung `scripts/run_all.py`

## Ziel

`run_all.py` soll schrittweise von einem monolithischen Tageslauf in eine fachlich geschnittene Pipeline ueberfuehrt werden. Ziel ist gleicher Output bei besserer Wartbarkeit, messbaren Laufzeiten und spaeter gezielten Teilneuberechnungen nach manuellen Korrekturen.

## Umgesetzter Stand

Dieser Commit fuehrt die erste risikoarme Bruecke ein:

- `scripts/pipeline/context.py`
  - zentraler `PipelineContext` fuer Projektpfade und Fachparameter
  - enthaelt bereits `overlap_tolerance_minutes = 5` als Zielparameter fuer die bestehende 5-Minuten-Toleranz
- `scripts/pipeline/rebuild_modes.py`
  - Zielmodi `FULL_IMPORT_REBUILD`, `FULL_REBUILD_FROM_RAW`, `OVERRIDE_REBUILD`, `EXPORT_REBUILD`
  - aktuell produktiv angebunden ist nur `FULL_IMPORT_REBUILD`
- `scripts/pipeline/step_result.py`
  - einheitliches Status- und Laufzeitmodell je Pipeline-Schritt
- `scripts/pipeline/runner.py`
  - fuehrt den bestehenden Tageslauf aus `run_all.py` als gemessenen Legacy-Step aus
  - schreibt Step-Logs nach `data/04_logs/<run_id>_pipeline_steps.json`
- `scripts/run_pipeline.py`
  - alternativer Einstiegspunkt fuer die neue Pipeline-Struktur

Die bestehende Fachlogik in `run_all.py` wurde bewusst noch nicht veraendert. Dadurch bleibt das Risiko gering und der bisherige Start ueber `scripts/run_all.py` funktioniert weiterhin.

## Start

Bisheriger Einstieg:

```powershell
.\.venv\Scripts\python.exe scripts\run_all.py
```

Neuer modularer Einstieg:

```powershell
.\.venv\Scripts\python.exe scripts\run_pipeline.py
```

Explizit mit Modus:

```powershell
.\.venv\Scripts\python.exe scripts\run_pipeline.py --mode FULL_IMPORT_REBUILD
```

## Zielbild der Pipeline-Schichten

```text
scripts/pipeline/
  context.py
  rebuild_modes.py
  step_result.py
  runner.py

  raw_import.py
  reference_import.py
  manual_overrides.py
  staging_loco_events.py
  transport_routes.py
  core_timeline.py
  findings.py
  quality_gate.py
  exports.py
  csv_outputs.py
```

## Rebuild Modes

| Modus | Ziel | Status |
| --- | --- | --- |
| `FULL_IMPORT_REBUILD` | CSV/Azure neu laden, Raw neu importieren, alles neu berechnen | angebunden ueber Legacy-Full-Rebuild |
| `FULL_REBUILD_FROM_RAW` | bestehende Raw-Schicht verwenden, alles ab Raw neu berechnen | Zielbild |
| `OVERRIDE_REBUILD` | Raw beibehalten, nur Overrides, Staging, Core, Findings, Gate und Export neu | Zielbild fuer schnelle Korrekturen |
| `EXPORT_REBUILD` | nur Exporttabellen und Dateien neu erzeugen | Zielbild |

## Empfohlene naechste Schritte

1. `run_all.py` mechanisch in fachliche Module zerlegen, ohne SQL/Fachlogik zu veraendern.
2. Jeden fachlichen Abschnitt als eigenen `PipelineStep` im Runner verdrahten.
3. Step-Laufzeiten im UI sichtbar machen.
4. `OVERRIDE_REBUILD` implementieren, damit manuelle Korrekturen nicht mehr den kompletten Import ausloesen.
5. Langfristig Raw-DuckDB-Schicht einfuehren:

```text
data/02_duckdb/
  netzentgelt_raw.duckdb
  netzentgelt_work.duckdb
  netzentgelt.duckdb
```

## Wichtige Leitplanken

- Keine produktiven Rohdaten veraendern.
- `netzentgelt.duckdb` nur nach erfolgreichem Lauf atomar ersetzen.
- Fachlicher Output muss vor und nach jedem Refactoring identisch bleiben.
- Performance erst nach Messung optimieren, nicht nach Gefuehl.
- Korrekturziel bleibt: gefuehlte Laufzeit im UI im Bereich weniger Sekunden durch Queue/Background-Run und `OVERRIDE_REBUILD`.
