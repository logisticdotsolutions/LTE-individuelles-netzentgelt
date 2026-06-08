@echo off
setlocal
echo ========================================================================
echo Netzentgelt Rule Engine Diagnostic Phase 6A - READ ONLY ANALYSE
echo ========================================================================
.venv\Scripts\python.exe scripts\rule_engine_diagnostic_phase6a.py
if errorlevel 1 (
  echo.
  echo FEHLER: Diagnose fehlgeschlagen.
  exit /b 1
)
echo.
echo OK: Diagnose abgeschlossen. Bericht liegt unter data\04_logs.
exit /b 0
