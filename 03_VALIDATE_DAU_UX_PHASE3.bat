@echo off
setlocal
cd /d "%~dp0"
echo ================================================================
echo Netzentgelt Phase 3 - DAU UX - VALIDIEREN
echo ================================================================
.venv\Scripts\python.exe validate_netzentgelt_dau_ux_phase3.py
if errorlevel 1 (
  echo.
  echo FEHLER: Validierung fehlgeschlagen.
  exit /b 1
)
echo.
echo OK: DAU-UX ist syntaktisch und strukturell validiert.
