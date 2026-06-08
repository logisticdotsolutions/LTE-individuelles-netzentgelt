@echo off
setlocal
echo ========================================================================
echo Netzentgelt Rule Engine Hardening Phase 6D - PAKET SELBSTTEST
echo ========================================================================
.venv\Scripts\python.exe package_selftest_rule_engine_hardening_phase6d.py
if errorlevel 1 (
  echo.
  echo FEHLER: Paket-Selbsttest fehlgeschlagen.
  exit /b 1
)
echo.
echo OK: Paket-Selbsttest erfolgreich.
exit /b 0
