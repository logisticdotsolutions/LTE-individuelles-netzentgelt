@echo off
setlocal
cd /d "%~dp0"
set "PYTHON=.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
echo ================================================================
echo Netzentgelt MVP Phase 5A - Manuelle Overrides - VERIFY CODE
echo ================================================================
"%PYTHON%" verify_manual_override_phase5a_installation.py --project-root .
if errorlevel 1 (
  echo.
  echo FEHLER: Verifikation fehlgeschlagen.
  exit /b 1
)
echo.
echo Code-Verifikation erfolgreich.
