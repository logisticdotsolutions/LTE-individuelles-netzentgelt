# Netzentgelt MVP - Repository Cleanup Phase 7C

Dieses Paket wird **außerhalb** des Repositorys entpackt und ausgeführt.
Es bereinigt bekannte Einmal-Artefakte aus Patch-Installationen, lokale Backups,
Testberichte, Cache-Verzeichnisse und alte Phase-6-Diagnosehelfer.

Produktive Dateien bleiben geschützt. Insbesondere bleiben erhalten:

- `RUN_TESTS.bat` und `RUN_TESTS.ps1`
- `app/app.py`
- `scripts/run_all.py`
- produktive Hardening-Module Phase 6B, 6C und 6D
- `scripts/pipeline_test_ui_module.py`
- die vollständige Testsuite unter `tests/`
- Mapping-Dateien und Templates

Laufdaten wie Rohdaten, DuckDBs, Exporte und Logs werden bei versehentlichem
Tracking nur aus Git gelöst. Die lokalen Dateien bleiben erhalten.

## Reihenfolge

Im Repository-Stamm ausführen:

```bat
C:\Pfad\zum\Cleanup\01_DRY_RUN_REPOSITORY_CLEANUP.bat
C:\Pfad\zum\Cleanup\02_APPLY_REPOSITORY_CLEANUP.bat
RUN_TESTS.bat
C:\Pfad\zum\Cleanup\04_CREATE_LOCAL_CLEANUP_COMMIT.bat
```

Danach `git status` prüfen und bewusst selbst pushen.

## Rollback vor dem Commit

```bat
C:\Pfad\zum\Cleanup\03_ROLLBACK_REPOSITORY_CLEANUP.bat
```

Backups werden außerhalb des Repositorys angelegt:

```text
..\_netzentgelt_cleanup_backups\
```

## Wichtiger Sicherheitscheck

Das Cleanup prüft getrackte Dateinamen auf Rohdaten, DuckDBs, Exporte, Logs,
`.env`, Zertifikate und Secret-Dateien. Falls jemals echte Zugangsdaten in das
öffentliche Repository gelangt sind, genügt ein normaler Lösch-Commit nicht:
Zugangsdaten müssen rotiert und die Git-Historie separat bereinigt werden.
