@echo off
setlocal
cd /d "%~dp0"

echo ================================================================
echo Netzentgelt Phase 2 - ROLLBACK
echo ================================================================

.venv\Scripts\python.exe rollback_netzentgelt_quality_gate_phase2.py
if errorlevel 1 (
    echo.
    echo FEHLER: Rollback konnte nicht abgeschlossen werden.
    exit /b 1
)

echo.
echo Rollback erfolgreich abgeschlossen.
endlocal
