@echo off
setlocal
echo ========================================================================
echo Netzentgelt Rule Engine Hardening Phase 6C - PIPELINE UND VERIFIKATION
echo ========================================================================
.venv\Scripts\python.exe scripts\run_pipeline_verify_rule_engine_hardening_phase6c.py
if errorlevel 1 (
  echo.
  echo FEHLER: Pipeline oder Verifikation fehlgeschlagen. Vorheriger Datenstand wurde wiederhergestellt.
  exit /b 1
)
echo.
echo OK: Pipeline und Verifikation erfolgreich.
exit /b 0
