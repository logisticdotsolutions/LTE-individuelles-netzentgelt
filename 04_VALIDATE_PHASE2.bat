@echo off
setlocal
cd /d "%~dp0"

echo ================================================================
echo Netzentgelt Phase 2 - BESTEHENDE DUCKDB VALIDIEREN
echo ================================================================

.venv\Scripts\python.exe validate_netzentgelt_quality_gate_phase2.py
if errorlevel 1 exit /b 1

endlocal
