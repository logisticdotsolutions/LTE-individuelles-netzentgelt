@echo off
setlocal
cd /d "%~dp0"
echo ================================================================
echo Netzentgelt Operational Day Filter Phase 5C - DRY RUN
echo ================================================================
.venv\Scripts\python.exe apply_operational_day_filter_phase5c.py dry-run --project-root .
if errorlevel 1 (
  echo.
  echo FEHLER: Dry Run fehlgeschlagen. Keine Dateien wurden veraendert.
  exit /b 1
)
echo.
echo Dry Run erfolgreich. Keine Dateien wurden veraendert.
