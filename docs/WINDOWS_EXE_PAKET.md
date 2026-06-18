# Windows-EXE-Paket fuer Netzentgelt MVP

## Ziel

Dieses Packaging erzeugt ein portables Windows-ZIP mit einer `NetzentgeltMVP.exe`.
Der Kollege muss kein Python installieren. Er muss das ZIP nur entpacken und die EXE starten.

Wichtig: Bei Streamlit ist ein Ordner-/ZIP-Paket stabiler als eine einzelne One-File-EXE, weil Streamlit statische Dateien, Python-Abhaengigkeiten und lokale Datenverzeichnisse benoetigt.

## Build auf der Entwickler-Workstation

Einmal aus dem Repository-Root ausfuehren:

```powershell
.\BUILD_WINDOWS_EXE.bat
```

Wenn die automatische Erkennung den falschen Streamlit-Einstieg findet, den Einstieg explizit uebergeben:

```powershell
.\BUILD_WINDOWS_EXE.bat scripts\DEINE_STREAMLIT_APP.py
```

Das Build-Skript installiert die Runtime- und Build-Abhaengigkeiten aus `requirements-build.txt` und erzeugt danach:

```text
dist\NetzentgeltMVP_Windows_Portable.zip
```

## Weitergabe an Kollegen

1. `dist\NetzentgeltMVP_Windows_Portable.zip` senden.
2. Kollege entpackt das ZIP lokal, z. B. nach `C:\LTE\NetzentgeltMVP`.
3. Kollege startet `NetzentgeltMVP.exe`.
4. Die lokale Streamlit-Oberflaeche oeffnet sich im Browser unter `http://127.0.0.1:<Port>`.

## Fachlicher Hinweis

Das ist eine lokale Einzelplatz-Auslieferung. Mehrere Personen arbeiten damit nicht automatisch auf demselben Datenstand. Fuer echten Mehrbenutzerbetrieb braucht es weiterhin eine zentrale Bereitstellung, z. B. VM/Webserver, zentrale Datenbank und geregelte Benutzer-/Rechteverwaltung.

## Typische Stolpersteine

- Windows Defender oder Unternehmens-AV kann eine selbstgebaute EXE blockieren.
- Der Kollege muss das ZIP entpacken; Start direkt aus dem ZIP funktioniert nicht sauber.
- Schreibrechte im Zielordner muessen vorhanden sein, wenn Korrekturen, Exporte oder lokale Datenbanken geschrieben werden.
- Bei produktiven Daten ist die ZIP-Verteilung nur als UAT-/Pilot-Loesung geeignet.

## Validierung nach dem Build

Nach dem Erzeugen des ZIPs lokal testen:

```powershell
Expand-Archive .\dist\NetzentgeltMVP_Windows_Portable.zip -DestinationPath .\dist\_smoke_exe -Force
.\dist\_smoke_exe\NetzentgeltMVP.exe
```

Danach pruefen:

- Browser oeffnet sich.
- Startseite der Anwendung wird geladen.
- Testdaten/Mappingdaten werden gefunden.
- Ein Export kann erzeugt werden.
- Korrekturen werden gespeichert und nach Neustart wieder geladen.
