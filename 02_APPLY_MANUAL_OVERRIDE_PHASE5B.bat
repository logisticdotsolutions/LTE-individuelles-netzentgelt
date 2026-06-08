@echo off
setlocal
cd /d "%~dp0"
echo ================================================================
echo Netzentgelt Phase 5B Systemvorschlaege - APPLY
echo ================================================================
set "PYTHON_EXE=.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"
"%PYTHON_EXE%" apply_netzentgelt_manual_override_phase5b.py --project-root . --apply
if errorlevel 1 (
  echo.
  echo FEHLER: Anwendung fehlgeschlagen. Bitte Rollback pruefen.
  exit /b 1
)
echo.
echo Phase 5B wurde angewandt.
