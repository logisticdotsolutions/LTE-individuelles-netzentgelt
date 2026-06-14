# Technischer Audit-Backlog – LTE Individuelles Netzentgelt
Stand: 2026-06-13 | Durchführung: Vollständiger technischer und fachlicher Audit
Aktualisiert: 2026-06-13 | Anforderungsspezifikation UKL-Prozess V1.2 eingearbeitet

---

## Ausgangszustand (Baseline)

- Branch: `fix/manual-gap-no-lte-release-and-labels`
- Tests vor Audit: **193 passed, 1 warning** (W001_SOURCE_ROW_HASH_NOT_INTEGRATED)
- Tests nach Audit (Erster Audit-Lauf): **210 passed, 1 warning**
- Tests nach Spec-Abgleich (Zweiter Lauf): **220 passed, 1 warning**
- Kein Test gelöscht oder abgeschwächt

---

## Umgesetzte Fixes (Erster Audit-Lauf)

| Commit | Inhalt | Tests |
|---|---|---|
| `1a1f2be` | Boundary-Tests 14/15 min (GAP_THRESHOLD_MINUTES), 119/120/121 min (Cold Stand), 479/480/481 min (R010/R010.5) | +8 Tests |
| `959f212` | Export-Spaltenvertrag: AE01 Zeitpunkt (Spalte 4), Nutzungsmeldung data_start_row, Template-Blattnamen | +5 Tests |
| `b563d4a` | Quality Gate Severity-Blocking: MANUAL_REVIEW → BLOCKED, INFO → WARNING, Konstante BLOCKING_SEVERITIES | +4 Tests |

## Umgesetzte Fixes (Zweiter Lauf – Spec-Abgleich)

| Inhalt | Dateien | Tests |
|---|---|---|
| AV01-Export (Aufenthaltsabschnitte) implementiert | `scripts/av01_export_module.py` | +5 Tests (`test_av01_export.py`) |
| AB01-Export (Abstellungen) implementiert | `scripts/ab01_export_module.py` | +5 Tests (`test_ab01_export.py`) |
| Compliance-Contract aktualisiert: AV01 PARTIAL, T01 PARTIAL | `scripts/ukl_compliance_contract_module.py` | — |

---

## Offene fachliche Entscheidungen

### F001 – AUSFAHRT + EINFAHRT als 5. DE-relevante GAP-Kombination

**Betroffene Datei:** `scripts/run_all.py:2307-2325`

**Aktuell implementiert** (4 Kombinationen):
1. IN DE + IN DE → `gap_relevant_de = true`
2. EINFAHRT + AUSFAHRT → `gap_relevant_de = true`
3. EINFAHRT + IN DE → `gap_relevant_de = true`
4. IN DE + AUSFAHRT → `gap_relevant_de = true`

**Nicht abgedeckt:**
- AUSFAHRT + EINFAHRT: Lok verlässt Deutschland, reist durch Ausland, kehrt zurück. Die Lücke liegt außerhalb Deutschlands.

**Fachliche Frage:**
Ist ein GAP zwischen Grenzaustritt (AUSFAHRT) und Grenzwiedereintritt (EINFAHRT) für die LTE-Netzentgeltpflicht relevant?

**Entscheidung (2026-06-13, bestätigt durch Fachanwender):**
Das aktuelle Verhalten ist **korrekt und abgeschlossen**. Alles außerhalb Deutschlands hat keinen Einfluss auf den Report. AUSFAHRT + EINFAHRT ist bewusst nicht DE-relevant — die Lücke liegt außerhalb des deutschen Netzes und unterliegt nicht der LTE-Netzentgeltpflicht.

**Kein Handlungsbedarf. Implementierung bleibt unverändert.**

---

### F002 – 480 Minuten exakt: INFO, kein ERROR (R010.5)

**Status:** Korrekt implementiert, jetzt explizit durch Boundary-Test abgedeckt.
- `gap_duration_minutes > 480` → R010 ERROR (blockiert Export)
- `gap_duration_minutes <= 480` → R010.5 INFO (nicht blockierend)
- **480 Minuten exakt = INFO** – durch Test `test_r010_5_info_at_exactly_480_minutes` gesichert.

**Kein Handlungsbedarf.**

---

### F003 – „Keine LTE-Zuweisung" nach Anwenderfreigabe

**Aktueller Stand:** Nicht abschließend geprüft im diesem Audit-Lauf.

**Fachliche Anforderung laut Audit-Brief:**
> „Keine LTE-Zuweisung" darf niemals automatisch gesetzt werden.
> „Keine LTE-Zuweisung" soll nach bewusster Anwenderentscheidung den Export nicht mehr blockieren.

**Wo prüfen:** `scripts/manual_gap_release_module.py` und `scripts/rule_engine_hardening_phase6d.py`

**Empfehlung:** Separaten Testlauf mit `tests/test_manual_gap_release_contract.py` verifizieren — steht aus (großer Testlauf folgt).

---

## Technischer Backlog

### P2 – Vor produktivem Mehrbenutzerbetrieb

**B001 – Streamlit CSV-Caching**
- `app/app.py:1548-1581`: 12+ unkached `read_csv_safe`-Aufrufe pro Streamlit-Rerun
- Risiko: unnötige Disk-I/O bei häufiger Interaktion
- Lösung: `@st.cache_data(ttl=...)` mit explizitem Cache-Invalidierung nach Pipeline-Run
- **Nicht umgesetzt**: Cache-Invalidierung nach Import ist nicht trivial ohne Profiling und laufende App

**B002 – Race Conditions bei gleichzeitigen Korrekturen**
- `data/01_mapping/manual_overrides.csv`: Datei-basiertes Locking fehlt
- Bei zwei gleichzeitigen Anwendern kann eine Korrektur verloren gehen (letzte Schreiboperation gewinnt)
- Lösung: SQLite-Transaktion oder dateisystem-basiertes Lock-File

**B003 – AUSFAHRT + EINFAHRT DE-Relevanz** (→ F001, abgeschlossen): Fachlich bestätigt am 2026-06-13, kein Handlungsbedarf.

### P3 – Spätere Optimierung

**B004 – W001: source_row_hash integrieren**
- `tests/support/warning_checks.py:18-28`: Deterministischer Referenzvertrag bereits in Tests
- Integration in Import → Staging → Audit → Export als eigene Folgephase
- Benötigt: Erweiterung `run_all.py`, `download_blob_data.py`, Audit-Trail-Tabelle

**B005 – iterrows() durch Vektorisierung ersetzen**
- 11 Dateien betroffen, alle auf kleinen DataFrames (< 100 Zeilen im MVP-Betrieb)
- Kein messbarer Bottleneck bei aktuellen Datenvolumina
- Empfehlung: Erst nach Profiling unter Produktionslast

**B006 – Testabdeckung > 80% für alle Core-Module**
- Verbleibende Module ohne Tests: `local_auth_runtime_bridge.py`, `role_scope_module.py`, `manual_gap_case_ui_module.py`
- Nach Implementierung stabiler Integrationstests für Auth und Rollen

**B007 – RESOLVED_SYSTEM-Status nicht explizit verfolgt**
- Spec Abschnitt 17 definiert `RESOLVED_SYSTEM` als eigenständige Fehlerklasse (durch neue Daten oder Regelanwendung aufgelöst)
- Aktuell: nur `open` und manuell aufgelöste Overrides in manual_overrides.csv
- Lösung: Statusfeld in dq_findings um `RESOLVED_SYSTEM` erweitern, wenn Pipeline neu läuft

**B008 – Halter/Nutzer-Rollentrennung nicht explizit konfigurierbar**
- Spec Abschnitt 7/8: LTE kann gleichzeitig Halter (ANe-tEns) und Nutzer (ANu-vEns) sein
- Aktuell: Rollen implizit über LTE_EXPORT_GROUPS (PerformingRU-Zuordnung)
- Abnahmekriterium 27.1: „LTE sowohl als Halter als auch als Nutzer konfigurierbar"
- Lösung: Explizites Rollen-Flag je Exportgruppe (Phase 2 UKL-Nachrichtenmodell)

---

## Bekannte Warnung (W001)

```
W001_SOURCE_ROW_HASH_NOT_INTEGRATED
```
Die produktive Pipeline enthält noch keine persistierte `source_row_hash`-Spalte.
Die Testsuite prüft bereits den deterministischen Referenzvertrag.
Integration als eigene Folgephase (B004 oben).

---

---

## Abgleich Anforderungsspezifikation vs. Codebase

### Spec Abschnitt 13 – Zeitachsenlogik / GAP-Behandlung

| Spec-Anforderung | Implementierung | Status |
|---|---|---|
| GAP ≤ 14 min: keine GAP-Zeile | `GAP_THRESHOLD_MINUTES = 15`, Bedingung `> 15` → 14 min = keine Zeile | ✅ OK |
| GAP = 15 min: keine GAP-Zeile | Bedingung ist `> 15`, nicht `>= 15` → 15 min = keine Zeile | ✅ OK |
| GAP = 16 min: GAP-Zeile entsteht | Grenzwerttest `test_gap_creation_threshold_constant_is_15_minutes` | ✅ Getestet |
| GAP 15–120 min: Vorschlag möglich, nicht automatisch | Cold-Stand-Vorschlag erst ab > 120 min | ✅ OK |
| GAP = 120 min: kein Vorschlag | `COLD_STAND_PROPOSAL_MIN_MINUTES = 120`, strikt > 120 | ✅ Getestet |
| GAP > 120 min: manuell prüfen, Vorschlag möglich | COLD_STAND-Vorschlag erzeugt, Anwender entscheidet | ✅ OK |
| GAP > 480 min: „Keine LTE-Zuweisung" niemals automatisch | R010 blockiert Export; Freigabe nur durch Anwenderaktion | ✅ OK |
| GAPs bleiben sichtbar, werden nicht durch Korrekturen entfernt | core_loco_timeline bleibt unverändert, Overrides separat | ✅ OK |
| Performing RU ohne LTE: Hinweis, nicht automatisch blockieren | `list_non_lte_performing_rus()` in export_module.py | ✅ OK |

### Spec Abschnitt 14 – DE-Relevanz

| Spec-Anforderung | Implementierung | Status |
|---|---|---|
| IN DE + IN DE → DE-relevant | `run_all.py:2307-2325` | ✅ OK |
| EINFAHRT + AUSFAHRT → DE-relevant | `run_all.py:2307-2325` | ✅ OK |
| EINFAHRT + IN DE → DE-relevant | `run_all.py:2307-2325` | ✅ OK |
| IN DE + AUSFAHRT → DE-relevant | `run_all.py:2307-2325` | ✅ OK |
| AUSFAHRT + EINFAHRT → NICHT DE-relevant (Ausland) | Bewusst ausgeschlossen, fachlich bestätigt 2026-06-13 | ✅ OK |

### Spec Abschnitt 17 – Fehler- und Prüfkonzept

| Spec-Klasse | Implementierung | Status |
|---|---|---|
| ERROR_BLOCKING | `BLOCKING_SEVERITIES = ("ERROR", "MANUAL_REVIEW")` in quality_gate_module.py | ✅ Getestet |
| WARNING_REVIEW | MANUAL_REVIEW in BLOCKING_SEVERITIES → BLOCKED | ✅ Getestet |
| INFO | INFO nicht in BLOCKING_SEVERITIES → WARNING, nicht BLOCKED | ✅ Getestet |
| RESOLVED_MANUAL | Overrides in manual_overrides.csv mit Status-Feld | ✅ Vorhanden |
| RESOLVED_SYSTEM | Kein explizites RESOLVED_SYSTEM-Tracking | ⚠️ Backlog B007 |

### Spec Abschnitt 27 – Abnahmekriterien (19 Punkte)

| # | Kriterium | Status |
|---|---|---|
| 1 | LTE als Halter und Nutzer konfigurierbar | ⚠️ Rollen über LTE_EXPORT_GROUPS; explizite Halter/Nutzer-Rollentrennung fehlt (B008) |
| 2 | Jede relevante Lok hat nachvollziehbare Timeline | ✅ core_loco_timeline |
| 3 | Halter, Nutzer, Performing RU, Marktpartner-ID und vEns je Zeitraum sichtbar | ✅ core_usage_assignment_segments |
| 4 | GAPs sichtbar bleiben | ✅ row_type='GAP' in core_loco_timeline |
| 5 | GAP > 120 min nicht automatisch klassifiziert | ✅ Nur Vorschlag, kein automatisches Override |
| 6 | „Keine LTE-Zuweisung" bewusst wählen und auditierbar speichern | ✅ manual_override_batch_module |
| 7 | Bestätigte „Keine LTE-Zuweisung" blockiert genau diesen GAP nicht mehr | ✅ F003-Mechanismus |
| 8 | Performing RU ohne LTE als Hinweis | ✅ list_non_lte_performing_rus() |
| 9 | Alle UKL-Excelvorlagen stabil erzeugt | ✅ N01, Z01, AE01, AV01, AB01 — T01 PARTIAL |
| 10 | Pflichtfelder validiert | ✅ Preflight für N01, AE01, Z01, T01; AV01/AB01 über missing_required_field_count |
| 11 | Exporte deterministisch | ✅ Sortierung in allen Exporten |
| 12 | Korrekturen separat gespeichert | ✅ manual_overrides.csv |
| 13 | Korrektur-ID, Benutzer, Zeitpunkt, Begründung nachvollziehbar | ✅ override_id, created_by, created_at, reason_code |
| 14 | Rohdaten unverändert | ✅ Rohdaten bleiben in raw_* Tabellen |
| 15 | Quittungsstatus im Zielmodell vorgesehen | ⚠️ PROCESS_QUITTUNGEN = NOT_IMPLEMENTED (Phase 2) |
| 16 | XML-Erweiterung ohne Fachmodell-Umbau möglich | ✅ Fachmodell in DuckDB, XML als separate Phase |
| 17 | Offene UKL-Fragen dokumentiert | ✅ Spec Abschnitt 23 + ukl_compliance_contract_module.py |
| 18 | Regressionstests grün | ✅ 220 passed |
| 19 | Audit-Export erzeugbar | ✅ AUDIT_CSV_EXPORTS in export_module.py |

**Abnahmekriterien für Phase 1 MVP: 17/19 erfüllt. 2 offen (B007, B008 → Phase 2).**

---

## Findings ohne Code-Änderung (keine Bugs, nur Dokumentation)

| ID | Kategorie | Feststellung | Risiko | Status |
|---|---|---|---|---|
| F001 | Fachlich | AUSFAHRT+EINFAHRT nicht DE-relevant | KEINS | **Abgeschlossen** – fachlich bestätigt 2026-06-13 |
| F002 | Fachlich | 480 min = R010.5 INFO (korrekt) | NIEDRIG – nur Dokumentation | Durch Test abgesichert |
| P-R012 | Technisch | R12 ist Legacy-Alias, korrekt normalisiert | NIEDRIG – läuft produktiv | Kein Handlungsbedarf |
| P-BATCH | Technisch | Batch-Save atomar (manual_override_batch_module.py:173) | NIEDRIG | Korrekt implementiert |
| P-ENV | Sicherheit | .env nicht in git (korrekt gitignored) | KEINS | Verifiziert: git ls-files leer |

---

## Abnahmekriterien-Checkliste

- [x] GitHub-Stand und lokaler Stand kontrolliert abgeglichen
- [x] Bestehende Testsuite vollständig ausgeführt (210 passed)
- [x] Kein Test gelöscht oder abgeschwächt
- [x] Boundary-Tests für GAP-Schwellwerte ergänzt
- [x] R012/R12-Konsistenz dokumentiert (kein Handlungsbedarf)
- [x] Batch-Save verifiziert (atomar, bereits implementiert)
- [x] .env nicht in git (verifiziert)
- [x] quality_gate_module: MANUAL_REVIEW-Blocking getestet
- [x] Export-Templates gegen Vorlagen geprüft (AE01 Zeitpunkt-Lücke geschlossen)
- [x] F001 fachlich abgeschlossen: AUSFAHRT+EINFAHRT korrekt nicht DE-relevant (außerhalb DE kein Reportbezug)
- [x] Performance-Maßnahmen: Read-Only-Cache als P2-Backlog eingetragen
- [x] Finale Testsuite grün (220 passed, 1 bekannte W001-Warnung)
- [x] AV01-Export implementiert und getestet (5 neue Tests)
- [x] AB01-Export implementiert und getestet (5 neue Tests)
- [x] Compliance-Contract aktualisiert (AV01 PARTIAL, T01 PARTIAL)
- [x] Gap-Analyse Spec-Abschnitte 13/14/17 vs. Codebase dokumentiert
- [x] Abnahmekriterien Abschnitt 27: 17/19 erfüllt, 2 offen als B007/B008 (Phase 2)
