@echo off
setlocal
cd /d "%~dp0"
set "PYTHON=.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
echo ================================================================
echo Netzentgelt MVP Phase 5A - Manuelle Overrides - APPLY
echo ================================================================
"%PYTHON%" apply_netzentgelt_manual_override_phase5a.py --project-root . --apply
if errorlevel 1 (
  echo.
  echo FEHLER: Anwendung fehlgeschlagen. Bitte Ausgabe pruefen.
  exit /b 1
)
echo.
echo Anwendung erfolgreich.
