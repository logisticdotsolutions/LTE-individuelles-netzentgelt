# Power BI MVP

Power BI soll im MVP ausschließlich lesen:

- `data/03_exports/core_loco_timeline.csv`
- `data/03_exports/dq_findings.csv`
- `data/03_exports/raw_import_run.csv`

Nicht in Power BI modellieren:

- Zeitachsenlogik
- Fehlerregeln
- Exportlogik
- manuelle Entscheidungslogik

Empfohlene Visuals:

1. Anzahl Bewegungen
2. Anzahl exportfähiger Zuordnungen
3. Fehler je Regel-ID
4. Fehler je Lok
5. Quote HIGH/MEDIUM/LOW Confidence
6. offene manuelle Prüffälle
