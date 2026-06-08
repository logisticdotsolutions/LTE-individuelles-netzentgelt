@echo off
setlocal
cd /d "%~dp0"
echo ================================================================
echo Netzentgelt Phase 5B Systemvorschlaege - ROLLBACK
echo ================================================================
set "PYTHON_EXE=.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"
"%PYTHON_EXE%" apply_netzentgelt_manual_override_phase5b.py --project-root . --rollback
if errorlevel 1 exit /b 1
echo.
echo Rollback erfolgreich.
