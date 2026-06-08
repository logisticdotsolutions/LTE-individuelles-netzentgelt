# Netzentgelt MVP – Architektur der automatisierten Testsuite

## 1. Zielbild

Die Testsuite ist als additive, nicht-invasive Qualitätsschicht aufgebaut. Sie verändert weder produktive Rohdaten unter `data/00_raw` noch produktive DuckDB-Dateien unter `data/02_duckdb`. Jeder DuckDB-Test nutzt eine In-Memory-Datenbank oder einen isolierten temporären Projektordner von pytest.

Die Suite prüft vier Ebenen getrennt:

1. **Unit-Verträge:** kleine Hilfsfunktionen, Normalisierung, Quoting, Datumsgrenzen und deterministische Rohdatenidentität.
2. **Fachregeln:** atomare Fixture-Tests für R001 bis R016 inklusive der bewusst deaktivierten oder separat behandelten MVP-Regeln.
3. **Modulintegration:** Cancelled-Transporte, manuelle Overrides, Audit Trail, Fallbacks, DE-Kontext, zentrale Segmente, Quality Gate sowie CSV- und XLSX-Ausgaben.
4. **Pipeline-Regression:** vollständiger Neuaufbau gegen einen isolierten temporären Projektordner mit definierten Soll-Kennzahlen.

## 2. Testpyramide

| Ebene | Zweck | Ausführung | Produktive Daten |
|---|---|---|---|
| Unit | Hilfsfunktionen und Referenzverträge | sehr schnell | kein Zugriff |
| Rule Fixtures | Regelverhalten R001–R016 | DuckDB `:memory:` | kein Zugriff |
| Integration | Modulketten und Schemakontrakte | DuckDB `:memory:` oder Temp-Datei | kein Zugriff |
| Smoke / Regression | vollständiger Tageslauf | temporärer Projektordner | kein Zugriff |

## 3. Regeln R001 bis R016

| Regel | Erwarteter Testvertrag |
|---|---|
| R001 | Erster fehlender Sequence-Zeitanker ist INFO; spätere Fälle sind ERROR. |
| R002 | Fehlende Abfahrt wird erkannt; nach 24 Stunden MANUAL_REVIEW. |
| R003 | Fehlende Ankunft wird erkannt; nach 24 Stunden MANUAL_REVIEW. |
| R004 | Abfahrt nach Ankunft ist ERROR. |
| R005 | Als separate Rohdaten-/UI-Prüfung dokumentiert; nicht als Core-Finding dupliziert. |
| R006 | Fehlende vEns erzeugt im MVP bewusst kein Finding. |
| R007 | Fehlende ANE_TENS-/Marktpartner-Zuordnung erzeugt im MVP bewusst kein Finding. |
| R008 | Entfernt: TfzE, tEns und Loknummer gelten im MVP als dieselbe Identifikation. |
| R009 | Fehlende PerformingRU ist MANUAL_REVIEW. |
| R010 | Sichere DE-relevante Unterbrechung über 8 Stunden ist ERROR. |
| R010.5 | Sichere DE-relevante Unterbrechung bis einschließlich 8 Stunden ist INFO. |
| R011 | Nur echte Intervallschnittmengen sind ERROR; direkte Anschlüsse bleiben zulässig. |
| R012 | Fehlende oder technische Dummy-Loknummern werden rohdatennah und verdichtet erkannt. |
| R013 | Fehlender Halter wird als sichtbarer MANUAL_REVIEW-Fall erzeugt. |
| R014 | Technische Dummy-Lok in der Timeline ist ERROR. |
| R015 | Unsichere GAP-Zeitgrenzen werden sichtbar; nach 24 Stunden MANUAL_REVIEW. |
| R016 | GAP-only-Lok-Tag erhält einen sichtbaren MANUAL_REVIEW-Prüffall. |

## 4. Rohdatenidentität

Der aktuelle Pipeline-Stand protokolliert Datei-Hashes. Die persistierte zeilenbezogene `source_row_hash` ist noch nicht integriert. Die Testsuite enthält deshalb bereits einen deterministischen Referenzvertrag:

- kanonische Spaltenreihenfolge,
- getrimmte skalare Werte,
- SHA-256 über die kanonische Zeilendarstellung,
- zusätzliche stabile Identität aus Quelldatei, Zeilenhash und Duplikatordinal.

Solange die produktive Pipeline diese Spalte nicht persistiert, erzeugt `warning_checks.py` die Warnung `W001_SOURCE_ROW_HASH_NOT_INTEGRATED`. Das ist bewusst ein WARNING und kein FAIL. Die Integration sollte als eigenständige Folgephase umgesetzt werden, weil sie Import-, Override- und Auditverträge berührt.

## 5. Berichte

`RUN_TESTS.bat` erzeugt je Lauf einen UTC-Zeitstempelordner unter `_test_reports/`:

- `pytest-report.html`: lesbarer HTML-Bericht,
- `pytest-junit.xml`: maschinenlesbarer Bericht für CI,
- `pytest-console.txt`: vollständige Terminalausgabe,
- `warnings.json`: offene WARNING-Verträge.

## 6. Lokale Nutzung

```bat
RUN_TESTS.bat -InstallDependencies
RUN_TESTS.bat
```

Für schnelle Entwicklungsschleifen ohne Smoke- und Regressionstest:

```bat
RUN_TESTS.bat -Fast
```

## 7. Spätere GitHub Actions

Der Workflow liegt bewusst deaktiviert unter `.github/workflows/netzentgelt-tests.yml.example`. Nach fachlicher Freigabe kann die Datei in `netzentgelt-tests.yml` umbenannt werden. Bis dahin verändert das Paket die CI/CD-Pipeline nicht.
