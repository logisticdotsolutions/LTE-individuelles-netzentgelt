# Windows-EXE-Paket fuer Netzentgelt MVP

## Ziel

Dieses Packaging erzeugt ein gesondertes Key-User-Paket mit einer `NetzentgeltMVP.exe`.
Der Key User muss kein Python installieren. Er muss nur das ZIP aus dem Key-User-Ordner entpacken und die EXE starten.

Wichtig: Bei Streamlit ist ein Ordner-/ZIP-Paket stabiler als eine einzelne One-File-EXE, weil Streamlit statische Dateien, Python-Abhaengigkeiten und lokale Datenverzeichnisse benoetigt.

## Build auf der Entwickler-Workstation

Einmal aus dem Repository-Root ausfuehren:

```powershell
.\BUILD_KEYUSER_PACKAGE.bat
```

Alternativ funktioniert weiterhin:

```powershell
.\BUILD_WINDOWS_EXE.bat
```

Wenn die automatische Erkennung den falschen Streamlit-Einstieg findet, den Einstieg explizit uebergeben:

```powershell
.\BUILD_KEYUSER_PACKAGE.bat scripts\DEINE_STREAMLIT_APP.py
```

Das Build-Skript installiert die Runtime- und Build-Abhaengigkeiten aus `requirements-build.txt` und erzeugt danach einen eindeutig getrennten Uebergabeordner:

```text
_keyuser_package\
  NetzentgeltMVP_KeyUser\
    NetzentgeltMVP.exe
    START_HIER.txt
    ...alle benoetigten Laufzeitdateien...
  NetzentgeltMVP_KeyUser.zip
```

## Weitergabe an Key User

Nur diesen Pfad weitergeben:

```text
_keyuser_package\NetzentgeltMVP_KeyUser.zip
```

Oder den gesamten Ordner:

```text
_keyuser_package\NetzentgeltMVP_KeyUser\
```

Nicht aus `dist`, `build`, `.venv`, `scripts` oder anderen Projektordnern manuell etwas zusammensuchen.

## Anleitung fuer den Key User

1. `NetzentgeltMVP_KeyUser.zip` lokal entpacken, z. B. nach `C:\LTE\NetzentgeltMVP_KeyUser`.
2. `START_HIER.txt` lesen.
3. `NetzentgeltMVP.exe` starten.
4. Die lokale Streamlit-Oberflaeche oeffnet sich im Browser unter `http://127.0.0.1:<Port>`.

## Fachlicher Hinweis

Das ist eine lokale Einzelplatz-Auslieferung. Mehrere Personen arbeiten damit nicht automatisch auf demselben Datenstand. Fuer echten Mehrbenutzerbetrieb braucht es weiterhin eine zentrale Bereitstellung, z. B. VM/Webserver, zentrale Datenbank und geregelte Benutzer-/Rechteverwaltung.

## Typische Stolpersteine

- Windows Defender oder Unternehmens-AV kann eine selbstgebaute EXE blockieren.
- Der Key User muss das ZIP entpacken; Start direkt aus dem ZIP funktioniert nicht sauber.
- Der gesamte entpackte Ordner muss zusammenbleiben.
- Schreibrechte im Zielordner muessen vorhanden sein, wenn Korrekturen, Exporte oder lokale Datenbanken geschrieben werden.
- Bei produktiven Daten ist die ZIP-Verteilung nur als UAT-/Pilot-Loesung geeignet.

## Validierung nach dem Build

Nach dem Erzeugen des Pakets lokal testen:

```powershell
Expand-Archive .\_keyuser_package\NetzentgeltMVP_KeyUser.zip -DestinationPath .\_keyuser_package\_smoke_exe -Force
.\_keyuser_package\_smoke_exe\NetzentgeltMVP_KeyUser\NetzentgeltMVP.exe
```

Danach pruefen:

- Browser oeffnet sich.
- Startseite der Anwendung wird geladen.
- Testdaten/Mappingdaten werden gefunden.
- Ein Export kann erzeugt werden.
- Korrekturen werden gespeichert und nach Neustart wieder geladen.
