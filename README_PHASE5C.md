# Netzentgelt MVP – Phase 5C: zentraler operativer Tagesfilter

## Zweck

Die UI zeigt standardmaessig den vollstaendigen vorgestrigen Kalendertag. Beispiel: Am 08.06.2026 ist automatisch der 06.06.2026 von 00:00 Uhr bis zum 07.06.2026 um 00:00 Uhr aktiv.

Der Filter gilt zentral fuer:

- Tagespruefung und Kennzahlen
- offene Aufgaben / Prueffaelle
- Lok-Detailpruefung
- Fallbearbeitung
- Systemvorschlaege
- technische Regelqueue
- technische R012-Rohdatenliste

Die Uhrzeit wird bei der Filterung ignoriert. Massgeblich ist ActualDeparture. Bei GAP-Zeilen ohne ActualDeparture wird der fachlich abgeleitete Periodenbeginn verwendet.

## RailCube-Hinweis

Eine Korrektur im MVP aendert keine Daten in RailCube. Fachlich erforderliche Berichtigungen muessen zusaetzlich in RailCube nachgezogen werden.

Aktive Overrides liegen separat in `data/01_mapping/manual_overrides.csv`. Ein neuer Rohdatenimport ueberschreibt diese Datei nicht. Bei jedem `run_all.py` werden aktive Overrides erneut auf den frischen Import angewandt. Nach einer Korrektur in RailCube ist der lokale Override im Cockpit zu deaktivieren.
