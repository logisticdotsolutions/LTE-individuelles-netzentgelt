@echo off
setlocal
cd /d "%~dp0"
echo ========================================================================
echo Netzentgelt Phase 5D - DRY RUN
echo ========================================================================
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" apply_netzentgelt_phase5d.py dry-run
) else (
    python apply_netzentgelt_phase5d.py dry-run
)
if errorlevel 1 (
    echo.
    echo FEHLER: Dry Run fehlgeschlagen. Keine Dateien wurden veraendert.
    exit /b 1
)
echo.
echo OK: Dry Run erfolgreich. Keine Dateien wurden veraendert.
