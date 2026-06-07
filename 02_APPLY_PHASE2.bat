@echo off
setlocal
cd /d "%~dp0"

echo ================================================================
echo Netzentgelt Phase 2 - PATCH ANWENDEN
echo ================================================================

.venv\Scripts\python.exe apply_netzentgelt_quality_gate_phase2.py
if errorlevel 1 (
    echo.
    echo FEHLER: Patch konnte nicht angewendet werden.
    exit /b 1
)

echo.
echo Patch erfolgreich. Nun 03_RUN_FULL_IMPORT_AND_PIPELINE_PHASE2.bat ausfuehren.
endlocal
