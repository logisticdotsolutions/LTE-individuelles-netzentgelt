# Portable SharePoint Release - Netzentgelt Tool

Ziel: Ein Kollege lädt ein ZIP von SharePoint herunter, entpackt es und startet das Tool per Doppelklick. Auf dem Zielrechner ist keine Python-Installation und kein Admin-Setup erforderlich.

## Paketinhalt

- `NetzentgeltTool.exe` als Starter
- App-Code aus `app/`
- Fachlogik aus `scripts/`
- Logos aus `data/06_pic/`
- Mappingdaten aus `data/01_mapping/`
- portable Laufzeitkonfiguration aus `config/portable_runtime.enc`
- zugehörige lokale Laufzeitdatei aus `config/portable_runtime.key`

## Nicht im Paket

- CSV-Rohdaten aus `data/00_raw/`
- fachliche DuckDB aus `data/02_duckdb/netzentgelt.duckdb`
- bestehende Exporte
- Korrektur- oder Auditstände aus einer Entwicklerinstallation
- Klartext-`.env`

## Release-Konfiguration erzeugen

```powershell
copy config\portable_runtime.template.json config\portable_runtime.private.json
```

Danach die private JSON-Datei lokal befüllen und anschließend erzeugen:

```powershell
.\.venv\Scripts\python.exe tools\write_portable_config.py --input config\portable_runtime.private.json
```

Die erzeugten Dateien `config\portable_runtime.enc` und `config\portable_runtime.key` werden für das portable Paket benötigt, aber nicht committed.

## Build erzeugen

```powershell
git pull
.\RUN_TESTS.bat
build\BUILD_PORTABLE_EXE_V2.bat
build\PACKAGE_SHAREPOINT_ZIP.bat 0.1.0
```

Ergebnis:

```text
release\NetzentgeltTool_0.1.0_windows_portable.zip
```

## Ablauf für Anwender

1. ZIP von SharePoint herunterladen
2. ZIP entpacken
3. `NetzentgeltTool.exe` doppelklicken
4. Browser öffnet sich lokal
5. Anmelden
6. Daten laden
7. Berechnung lokal starten
8. Export lokal erzeugen

## Hinweis

Die portable Variante ist für einen Pilotbetrieb und Keyuser-Tests gedacht. Für einen produktiven Mehrbenutzerbetrieb ist später eine zentral betriebene Webanwendung mit zentraler Authentifizierung und zentralem Secret-Handling sauberer.
