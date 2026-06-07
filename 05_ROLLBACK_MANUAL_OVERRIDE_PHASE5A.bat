@echo off
setlocal
cd /d "%~dp0"
set "PYTHON=.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
echo ================================================================
echo Netzentgelt MVP Phase 5A - Manuelle Overrides - ROLLBACK
echo ================================================================
"%PYTHON%" snapshot_manual_override_phase5a_runtime.py --project-root . --rollback
if errorlevel 1 (
  echo FEHLER: Runtime-Rollback fehlgeschlagen.
  exit /b 1
)
"%PYTHON%" apply_netzentgelt_manual_override_phase5a.py --project-root . --rollback
if errorlevel 1 (
  echo FEHLER: Code-Rollback fehlgeschlagen.
  exit /b 1
)
echo.
echo Rollback erfolgreich.
