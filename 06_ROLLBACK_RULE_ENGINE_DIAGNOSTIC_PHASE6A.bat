@echo off
setlocal
echo ========================================================================
echo Netzentgelt Rule Engine Diagnostic Phase 6A - ROLLBACK
echo ========================================================================
.venv\Scripts\python.exe apply_rule_engine_diagnostic_phase6a.py rollback
if errorlevel 1 (
  echo.
  echo FEHLER: Rollback fehlgeschlagen.
  exit /b 1
)
echo.
echo OK: Rollback abgeschlossen.
exit /b 0
