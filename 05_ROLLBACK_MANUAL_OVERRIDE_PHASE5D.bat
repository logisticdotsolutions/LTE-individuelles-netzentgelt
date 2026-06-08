@echo off
setlocal
cd /d "%~dp0"
echo ========================================================================
echo Netzentgelt Phase 5D - ROLLBACK
 echo ========================================================================
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" apply_netzentgelt_phase5d.py rollback
) else (
    python apply_netzentgelt_phase5d.py rollback
)
if errorlevel 1 exit /b 1
echo.
echo OK: Phase 5D wurde zurueckgerollt.
