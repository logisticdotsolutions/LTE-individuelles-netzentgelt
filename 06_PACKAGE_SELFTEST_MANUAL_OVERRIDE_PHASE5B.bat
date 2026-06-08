@echo off
setlocal
cd /d "%~dp0"
echo ================================================================
echo Netzentgelt Phase 5B Systemvorschlaege - PACKAGE SELFTEST
echo ================================================================
set "PYTHON_EXE=.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"
"%PYTHON_EXE%" package_selftest.py
if errorlevel 1 exit /b 1
echo.
echo Paket-Selbsttest erfolgreich.
