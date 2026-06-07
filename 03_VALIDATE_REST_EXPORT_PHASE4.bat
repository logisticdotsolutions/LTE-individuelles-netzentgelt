@echo off
setlocal
cd /d "%~dp0"
echo ================================================================
echo Netzentgelt Phase 4 - Rest-Exporte validieren
echo ================================================================
.venv\Scripts\python.exe validate_netzentgelt_rest_exports_phase4.py
if errorlevel 1 exit /b 1
