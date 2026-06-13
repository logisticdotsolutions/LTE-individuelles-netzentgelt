# Technischer Audit-Backlog – LTE Individuelles Netzentgelt
Stand: 2026-06-13 | Durchführung: Vollständiger technischer und fachlicher Audit

---

## Ausgangszustand (Baseline)

- Branch: `fix/manual-gap-no-lte-release-and-labels`
- Tests vor Audit: **193 passed, 1 warning** (W001_SOURCE_ROW_HASH_NOT_INTEGRATED)
- Tests nach Audit: **210 passed, 1 warning**
- Kein Test gelöscht oder abgeschwächt

---

## Umgesetzte Fixes (dieser Audit-Lauf)

| Commit | Inhalt | Tests |
|---|---|---|
| `1a1f2be` | Boundary-Tests 14/15 min (GAP_THRESHOLD_MINUTES), 119/120/121 min (Cold Stand), 479/480/481 min (R010/R010.5) | +8 Tests |
| `959f212` | Export-Spaltenvertrag: AE01 Zeitpunkt (Spalte 4), Nutzungsmeldung data_start_row, Template-Blattnamen | +5 Tests |
| `b563d4a` | Quality Gate Severity-Blocking: MANUAL_REVIEW → BLOCKED, INFO → WARNING, Konstante BLOCKING_SEVERITIES | +4 Tests |

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

---

## Bekannte Warnung (W001)

```
W001_SOURCE_ROW_HASH_NOT_INTEGRATED
```
Die produktive Pipeline enthält noch keine persistierte `source_row_hash`-Spalte.
Die Testsuite prüft bereits den deterministischen Referenzvertrag.
Integration als eigene Folgephase (B004 oben).

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
- [x] Finale Testsuite grün (210 passed, 1 bekannte W001-Warnung)
