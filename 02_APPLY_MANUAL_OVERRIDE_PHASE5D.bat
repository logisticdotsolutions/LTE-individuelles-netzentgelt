@echo off
setlocal
cd /d "%~dp0"
echo ========================================================================
echo Netzentgelt Phase 5D - APPLY
 echo ========================================================================
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" apply_netzentgelt_phase5d.py apply
) else (
    python apply_netzentgelt_phase5d.py apply
)
if errorlevel 1 (
    echo.
    echo FEHLER: Apply fehlgeschlagen. Automatischer Rollback wurde versucht.
    exit /b 1
)
echo.
echo OK: Phase 5D wurde angewandt.
