@echo off
setlocal
cd /d "%~dp0"
echo ================================================================
echo Netzentgelt Phase 5B Systemvorschlaege - FACHLICHER SMOKE TEST
echo ================================================================
set "PYTHON_EXE=.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"
"%PYTHON_EXE%" verify_manual_override_phase5b_logic.py --project-root .
if errorlevel 1 exit /b 1
echo.
echo Fachlicher Smoke-Test erfolgreich.
