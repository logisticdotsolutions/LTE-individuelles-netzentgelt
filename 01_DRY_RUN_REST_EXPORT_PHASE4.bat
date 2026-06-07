@echo off
setlocal
cd /d "%~dp0"
echo ================================================================
echo Netzentgelt Phase 4 - Rest-Exporte DRY RUN
echo ================================================================
.venv\Scripts\python.exe apply_netzentgelt_rest_exports_phase4.py --dry-run
if errorlevel 1 (
  echo.
  echo FEHLER: Dry Run ist fehlgeschlagen. Keine Dateien wurden veraendert.
  exit /b 1
)
echo.
echo Dry Run erfolgreich.
