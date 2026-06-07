@echo off
setlocal
cd /d "%~dp0"
echo ================================================================
echo Netzentgelt Cancelled Hotfix V2 - ROLLBACK
echo ================================================================
if exist ".venv\Scripts\python.exe" (
    set "PYTHON=.venv\Scripts\python.exe"
) else (
    set "PYTHON=python"
)
"%PYTHON%" apply_netzentgelt_cancelled_hotfix.py --rollback
if errorlevel 1 goto :error
"%PYTHON%" snapshot_cancelled_hotfix_runtime.py --restore-latest-if-present
if errorlevel 1 goto :error
echo.
echo ROLLBACK erfolgreich.
exit /b 0
:error
echo.
echo FEHLER: Rollback fehlgeschlagen.
exit /b 1
