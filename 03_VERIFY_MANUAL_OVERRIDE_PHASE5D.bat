@echo off
setlocal
cd /d "%~dp0"
echo ========================================================================
echo Netzentgelt Phase 5D - VERIFY
 echo ========================================================================
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" apply_netzentgelt_phase5d.py verify
) else (
    python apply_netzentgelt_phase5d.py verify
)
if errorlevel 1 exit /b 1
echo.
echo OK: Phase 5D Marker und Python-Syntax sind gueltig.
