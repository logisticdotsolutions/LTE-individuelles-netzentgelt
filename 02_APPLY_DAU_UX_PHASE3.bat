@echo off
setlocal
cd /d "%~dp0"
echo ================================================================
echo Netzentgelt Phase 3 - DAU UX - PATCH ANWENDEN
echo ================================================================
.venv\Scripts\python.exe apply_netzentgelt_dau_ux_phase3.py
if errorlevel 1 (
  echo.
  echo FEHLER: Patch konnte nicht angewendet werden.
  exit /b 1
)
echo.
echo OK: Patch erfolgreich angewendet.
