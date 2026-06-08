@echo off
setlocal
echo ========================================================================
echo Netzentgelt Rule Engine Hardening Phase 6B - CODE ROLLBACK
echo ========================================================================
.venv\Scripts\python.exe apply_rule_engine_hardening_phase6b.py rollback
if errorlevel 1 (
  echo.
  echo FEHLER: Rollback fehlgeschlagen.
  exit /b 1
)
echo.
echo OK: Code-Rollback abgeschlossen.
exit /b 0
