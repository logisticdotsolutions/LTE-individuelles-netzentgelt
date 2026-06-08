# Netzentgelt MVP - Phase 7A Fixture Hotfix v1.2

Dieser Hotfix aktualisiert ausschließlich zwei Testsuite-Dateien und die lokale Test-Startdatei `RUN_TESTS.ps1`. Produktive Skripte,
Rohdaten, Mapping-Dateien, Exporte und DuckDB-Dateien bleiben unverändert.

## Behobene Fixture-Probleme

1. `dq_global_export_blockers` enthält im Export-Fixture nun die produktiv erwartete Spalte `rule_id`.
2. Phase-6C-Kontextfixtures führen die bereits in der produktiven Timeline vorhandenen `next_origin_*`-Felder mit.
3. Der direkte R015-Test legt die Phase-6C-Spalten an, die im produktiven Ablauf durch `prepare_timeline_context_phase6c()` erzeugt werden.
4. Das DE-Segment-Fixture verwendet Grenzintervalle mit positiver DE-Dauer statt auf null gekappter Zeiträume.
5. `RUN_TESTS.ps1` setzt UTF-8 explizit, damit Umlaute in Windows PowerShell verständlich ausgegeben werden.

## Anwendung

Im Repository-Stamm ausführen:

```bat
C:\Pfad\zum\Hotfix\01_DRY_RUN_PHASE7A_FIXTURE_HOTFIX.bat
C:\Pfad\zum\Hotfix\02_APPLY_PHASE7A_FIXTURE_HOTFIX.bat
RUN_TESTS.bat
```

## Rollback

```bat
C:\Pfad\zum\Hotfix\03_ROLLBACK_PHASE7A_FIXTURE_HOTFIX.bat
```

## Lokaler Commit ohne Push

Nach erfolgreichem Testlauf:

```bat
C:\Pfad\zum\Hotfix\04_CREATE_LOCAL_COMMIT.bat
```
