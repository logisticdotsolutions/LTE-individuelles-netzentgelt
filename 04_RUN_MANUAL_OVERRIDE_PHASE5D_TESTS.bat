@echo off
setlocal
cd /d "%~dp0"
echo ========================================================================
echo Netzentgelt Phase 5D - LOGIKTESTS
 echo ========================================================================
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" test_phase5d_logic.py
) else (
    python test_phase5d_logic.py
)
if errorlevel 1 exit /b 1
echo.
echo OK: Phase 5D Logiktests erfolgreich.
