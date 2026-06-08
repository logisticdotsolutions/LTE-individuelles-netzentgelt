# Test Report – Netzentgelt MVP Phase 5B

## Geprüfte Grundlage

GitHub `main`:

```text
d276d8fb4b07382e1382d4ad9994f0fc636cbc1c
feat: add audited manual override cockpit
```

Die GitHub-Blob-SHAs der Phase-5A-Grundlage wurden vor Paketerstellung geprüft:

```text
scripts/manual_override_ui_module.py  7966929fba47f722a3dcd9b520526efb9f70bc63
scripts/manual_override_module.py     83f8c360512b768364ab3285baff041e8e030ca4
app/app.py                            4dfcdd217f240a10b3e84ad37079ab3be97b98ee
scripts/run_all.py                    7f9acb051c69708857054205567e993e487a1692
```

## Paket-Selbsttest

Erfolgreich geprüft:

- Dry-Run verändert keine Dateien
- Apply erzeugt automatisches Backup
- neue Engine wird angelegt
- Cockpitdatei wird vollständig ersetzt
- Windows-CRLF bleibt erhalten
- Python-Syntaxprüfung läuft nach Apply
- wiederholter Dry-Run nach Apply ist zulässig
- Rollback stellt Cockpitdatei bytegenau wieder her
- Rollback entfernt die zuvor nicht vorhandene Engine
- lokal veränderte Cockpitdatei wird sicher abgewiesen

## Fachlicher Smoke-Test

Erfolgreich geprüft:

- PerformingRU: identische vorherige und nachfolgende RU erzeugen HIGH-Vorschlag
- PerformingRU: widersprüchliche Nachbarn erzeugen LOW-Hinweis ohne Vorauswahl
- Loknummer: identische Fundstelle in beiden Transportquellen erzeugt HIGH-Vorschlag
- kalte Abstellung: Standzeit am selben Ort ab 480 Minuten erzeugt MEDIUM-Klassifikationsvorschlag
- gebrochene Ortskette: erzeugt MEDIUM-Klassifikationsvorschlag `MISSING_MOVEMENT`
- Grenzzeitanker: bestehende Richtungslogik erzeugt MEDIUM-Vorschlag
- Grenzereignis außerhalb Viertelstundenraster: erzeugt LOW-Prüfvorschlag
- Vorschlags-Engine öffnet DuckDB read-only und verändert keine Daten

## Ende-zu-Ende-Installationsprüfung

Auf CRLF-Projektsnapshot erfolgreich ausgeführt:

1. Dry-Run
2. Apply
3. Installationsprüfung
4. fachlicher Smoke-Test
5. Rollback
6. Prüfung, dass neue Engine nach Rollback entfernt wurde

## Bewusste Nicht-Automatisierung

Folgende Punkte bleiben fachlich kontrolliert:

- keine automatische Override-Erstellung
- keine automatische Freigabe kalter Abstellungen
- keine automatische Anwendung gerundeter Grenzzeiten
- keine Änderung des Quality Gates durch reine Vorschläge
- keine Änderung der DataLake-Rohdateien
