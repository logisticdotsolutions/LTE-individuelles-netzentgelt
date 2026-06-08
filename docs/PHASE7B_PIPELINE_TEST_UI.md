# Phase 7B - Pipeline- und Testcontroller in Streamlit

## Zweck

Der technische Tab stellt drei kontrollierte Aktionen bereit:

1. **Nur Tests starten**: führt ausschließlich die isolierte Testsuite aus.
2. **Pipeline + Tests**: baut DuckDB und Exporte über `scripts/run_all.py` neu auf und startet danach die Testsuite.
3. **Azure-Download + Pipeline + Tests**: lädt einen frischen Rohdatensnapshot, berechnet den Tageslauf und startet danach die Testsuite.

## Ergebnisanzeige

Nach jedem Testlauf werden angezeigt:

- PASS / FAIL / WARNING als Kennzahlen,
- jeder einzelne pytest-Test mit Status und Laufzeit,
- Fehlermeldung je fehlgeschlagenem Test,
- technische Schritte mit vollständiger Konsolenausgabe,
- Download des HTML-, JUnit-, Konsolen- und UI-Zusammenfassungsberichts.

## Sicherheitsgrenzen

Die Testsuite verwendet ausschließlich Fixtures und temporäre DuckDB-Dateien. Die Testaktion verändert keine produktiven Rohdaten und keine produktive DuckDB. Die Pipeline-Aktionen sind bewusst produktiv und verwenden weiterhin die abgesicherte Build- und Replace-Logik aus `run_all.py`.

## Vollabdeckung

Die Suite deckt die vereinbarten fachlichen Anforderungen vollständig ab: Regeln R001 bis R016, DE-Relevanz, GAPs, Grenzkontext, kalte Abstellungen, Overlaps, 24h-Cutoff, Cancelled-Transporte, Fallbacks, Overrides, Audit Trail, DE-Segmente, CSV/XLSX-Exporte, Schemaabweichungen, Rohdatenidentität, Pipeline-Smoke und Regression. Diese fachliche Abdeckung ist von einer 100-prozentigen Quellcode-Zeilenabdeckung zu unterscheiden.
