@echo off
setlocal
cd /d "%~dp0"
set "PYTHON=.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
echo ================================================================
echo Netzentgelt MVP Phase 5A - Paket-Selbsttest
echo ================================================================
"%PYTHON%" package_selftest.py
if errorlevel 1 exit /b 1
"%PYTHON%" verify_manual_override_phase5a.py
if errorlevel 1 exit /b 1
echo.
echo Paket-Selbsttest erfolgreich.
