@echo off
setlocal
cd /d "%~dp0"
echo ================================================================
echo Netzentgelt Phase 3 - DAU UX - ROLLBACK
echo ================================================================
.venv\Scripts\python.exe rollback_netzentgelt_dau_ux_phase3.py
if errorlevel 1 (
  echo.
  echo FEHLER: Rollback fehlgeschlagen.
  exit /b 1
)
echo.
echo OK: Letztes Phase-3-Backup wurde wiederhergestellt.
