@echo off
setlocal
cd /d "%~dp0"
set "PYTHON=.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
echo ================================================================
echo Netzentgelt MVP Phase 5A - Manuelle Overrides - DRY RUN
echo ================================================================
"%PYTHON%" apply_netzentgelt_manual_override_phase5a.py --project-root . --dry-run
if errorlevel 1 (
  echo.
  echo FEHLER: Dry Run fehlgeschlagen. Keine Dateien wurden veraendert.
  exit /b 1
)
echo.
echo Dry Run erfolgreich. Keine Dateien wurden veraendert.
