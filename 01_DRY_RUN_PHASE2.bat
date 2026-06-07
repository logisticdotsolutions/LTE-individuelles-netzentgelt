@echo off
setlocal
cd /d "%~dp0"

echo ================================================================
echo Netzentgelt Phase 2 - DRY RUN
echo ================================================================

.venv\Scripts\python.exe apply_netzentgelt_quality_gate_phase2.py --dry-run
if errorlevel 1 (
    echo.
    echo FEHLER: Dry Run ist fehlgeschlagen. Keine Dateien wurden veraendert.
    exit /b 1
)

echo.
echo Dry Run erfolgreich. Nun 02_APPLY_PHASE2.bat ausfuehren.
endlocal
