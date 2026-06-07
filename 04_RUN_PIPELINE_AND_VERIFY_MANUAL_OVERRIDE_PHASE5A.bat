@echo off
setlocal
cd /d "%~dp0"
set "PYTHON=.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
echo ================================================================
echo Netzentgelt MVP Phase 5A - Runtime Backup, Pipeline und Verify
echo ================================================================
"%PYTHON%" snapshot_manual_override_phase5a_runtime.py --project-root . --snapshot
if errorlevel 1 (
  echo FEHLER: Runtime-Backup fehlgeschlagen. Pipeline wurde nicht gestartet.
  exit /b 1
)
"%PYTHON%" scripts\run_all.py
if errorlevel 1 (
  echo.
  echo FEHLER: Pipeline fehlgeschlagen. Letzter produktiver DuckDB-Stand bleibt durch run_all.py erhalten.
  echo Fuer die Wiederherstellung der Exportdateien bitte 05_ROLLBACK_MANUAL_OVERRIDE_PHASE5A.bat ausfuehren.
  exit /b 1
)
"%PYTHON%" verify_manual_override_phase5a_installation.py --project-root . --require-db-tables
if errorlevel 1 (
  echo.
  echo FEHLER: Laufzeit-Verifikation fehlgeschlagen. Bitte Rollback ausfuehren.
  exit /b 1
)
echo.
echo Pipeline und Laufzeit-Verifikation erfolgreich.
