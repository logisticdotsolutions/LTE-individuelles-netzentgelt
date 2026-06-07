@echo off
setlocal
cd /d "%~dp0"
echo ================================================================
echo Netzentgelt Cancelled Hotfix V2 - PIPELINE + PRODUCTION VERIFY
echo ================================================================
if exist ".venv\Scripts\python.exe" (
    set "PYTHON=.venv\Scripts\python.exe"
) else (
    set "PYTHON=python"
)
"%PYTHON%" snapshot_cancelled_hotfix_runtime.py --backup
if errorlevel 1 goto :error
"%PYTHON%" scripts\run_all.py
if errorlevel 1 goto :error
"%PYTHON%" verify_cancelled_hotfix.py --production-db
if errorlevel 1 goto :error
echo.
echo PIPELINE und Produktionspruefung erfolgreich.
exit /b 0
:error
echo.
echo FEHLER: Pipeline oder Produktionspruefung fehlgeschlagen.
exit /b 1
