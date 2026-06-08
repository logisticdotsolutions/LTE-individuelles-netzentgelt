# Netzentgelt MVP – Test-Coverage-Matrix Phase 7A

## Abdeckung der geforderten Testbereiche

| Nr. | Anforderung | Umsetzung | Status |
|---:|---|---|---|
| 1 | Unit Tests für Hilfsfunktionen | `tests/test_unit_helpers.py` | PASS-konzipiert |
| 2 | DuckDB-Fixture-Tests für R001 bis R016 | `tests/test_rule_catalog_and_base_rules.py`, `tests/test_phase6b_rules_and_fallbacks.py`, `tests/test_phase6c_context_and_segments.py`, `tests/test_phase6d_quality_gate.py` | abgedeckt |
| 3 | DE-Relevanz, GAPs, Grenzkontext, kalte Abstellungen | `tests/test_phase6c_context_and_segments.py` | abgedeckt |
| 4 | Echte Überschneidungen und direkte Anschlussbewegungen | `tests/test_phase6b_rules_and_fallbacks.py`, `tests/test_phase6d_quality_gate.py` | abgedeckt |
| 5 | 24h-Cutoff | `tests/test_phase6b_rules_and_fallbacks.py` | abgedeckt |
| 6 | Cancelled-Transporte | `tests/test_cancelled_and_overrides.py` | abgedeckt |
| 7 | Halter-, vEns- und Marktpartner-Fallbacks | `tests/test_phase6b_rules_and_fallbacks.py` | abgedeckt |
| 8 | Manuelle Overrides und Audit Trail | `tests/test_cancelled_and_overrides.py` | abgedeckt |
| 9 | Zentrale DE-Segmente | `tests/test_phase6c_context_and_segments.py` | abgedeckt |
| 10 | CSV- und XLSX-Exporte | `tests/test_exports_csv_xlsx.py` | abgedeckt |
| 11 | Schemaänderungen und erwartete Spalten | `tests/test_schema_contracts.py` | abgedeckt |
| 12 | Stabile Rohdatenidentität und `source_row_hash` | `tests/support/raw_identity.py`, `tests/test_unit_helpers.py`, `tests/test_schema_contracts.py`, `tests/support/warning_checks.py` | Referenzvertrag abgedeckt; Produktivintegration als WARNING |
| 13 | Pipeline-Smoke-Test mit temporärer DuckDB | `tests/test_pipeline_smoke.py` | abgedeckt |
| 14 | Regressionstest gegen definierte Soll-Kennzahlen | `tests/test_regression_kpis.py`, `tests/fixtures/regression_expected.json` | abgedeckt |
| 15 | Ein einziges Startskript | `RUN_TESTS.bat`, `RUN_TESTS.ps1` | abgedeckt |
| 16 | Zusammenfassung PASS / FAIL / WARNING | `RUN_TESTS.ps1`, HTML-, JUnit-, Konsolen- und WARNING-Bericht | abgedeckt |

## Regelmatrix R001 bis R016

| Regel | Positivvertrag | Negativvertrag / Abgrenzung |
|---|---|---|
| R001 | Fehlender Zeitanker nach erster Bewegung erzeugt ERROR. | Erster fehlender Zeitanker bleibt INFO. |
| R002 | Fehlende Abfahrt wird erkannt und nach Cutoff hochgestuft. | Innerhalb 24h noch nicht hart blockierend. |
| R003 | Fehlende Ankunft wird erkannt und nach Cutoff hochgestuft. | Innerhalb 24h noch INFO. |
| R004 | Abfahrt nach Ankunft erzeugt ERROR. | Gültige Intervalle bleiben unauffällig. |
| R005 | Separate Rohdaten-/UI-Policy bleibt dokumentiert. | Kein doppeltes Core-Finding. |
| R006 | Bewusst deaktivierte MVP-Policy bleibt dokumentiert. | Kein Finding bei fehlender vEns. |
| R007 | Bewusst deaktivierte MVP-Policy bleibt dokumentiert. | Kein Finding bei fehlendem Mapping. |
| R008 | Entfernte Policy bleibt dokumentiert. | Gleiche Lok-/TfzE-Identifikation ist zulässig. |
| R009 | Fehlende PerformingRU erzeugt MANUAL_REVIEW. | Befüllte PerformingRU bleibt unauffällig. |
| R010 | Sichere DE-GAP über 8h erzeugt ERROR. | Nur DE-relevante GAPs greifen. |
| R010.5 | Sichere DE-GAP bis 8h erzeugt INFO. | Keine harte Blockierung. |
| R011 | Echte Intervallschnittmenge erzeugt ERROR. | Direkter zeitlicher Anschluss ist zulässig. |
| R012 | Fehlende und technische Dummy-Loks werden rohdatennah erkannt. | Cancelled-Transporte werden ausgeschlossen. |
| R013 | Fehlender Halter wird sichtbar. | Halter-Fallback verhindert unsichtbare Sperre. |
| R014 | Technische Dummy-Lok in Timeline wird sichtbar. | Reale Loknummer bleibt zulässig. |
| R015 | Unsichere GAP-Grenzen werden sichtbar. | Keine künstliche Ersatzdauer. |
| R016 | GAP-only-Lok-Tag wird sichtbar. | Keine stille Blockierung ohne Prüffall. |

## WARNING-Verträge

| Code | Bedeutung | Nächste Folgephase |
|---|---|---|
| `W001_SOURCE_ROW_HASH_NOT_INTEGRATED` | Datei-Hashes sind vorhanden, aber die persistierte zeilenbezogene Rohdatenidentität fehlt noch in der produktiven Pipeline. | Import-, Override- und Auditmodell um `source_row_hash` und stabile Duplikatordinal-Logik erweitern. |
| `W002_TEMPLATE_MISSING` | Eine produktive XLSX-Vorlage fehlt lokal. | Vorlage unter `data/05_templates` bereitstellen. |
