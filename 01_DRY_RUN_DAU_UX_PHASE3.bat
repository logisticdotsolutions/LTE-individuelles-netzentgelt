@echo off
setlocal
cd /d "%~dp0"
echo ================================================================
echo Netzentgelt Phase 3 - DAU UX - DRY RUN
echo ================================================================
.venv\Scripts\python.exe apply_netzentgelt_dau_ux_phase3.py --dry-run
if errorlevel 1 (
  echo.
  echo FEHLER: Dry Run ist fehlgeschlagen. Keine Dateien wurden veraendert.
  exit /b 1
)
echo.
echo OK: Dry Run erfolgreich. Keine Dateien wurden veraendert.
