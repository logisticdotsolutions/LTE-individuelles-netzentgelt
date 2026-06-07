@echo off
setlocal
cd /d "%~dp0"
echo ================================================================
echo Netzentgelt Cancelled Hotfix V2 - DRY RUN
echo ================================================================
if exist ".venv\Scripts\python.exe" (
    set "PYTHON=.venv\Scripts\python.exe"
) else (
    set "PYTHON=python"
)
"%PYTHON%" apply_netzentgelt_cancelled_hotfix.py --self-test
if errorlevel 1 goto :error
"%PYTHON%" apply_netzentgelt_cancelled_hotfix.py --dry-run
if errorlevel 1 goto :error
echo.
echo DRY RUN erfolgreich. Keine Projektdateien wurden veraendert.
exit /b 0
:error
echo.
echo FEHLER: Dry Run fehlgeschlagen. Keine Projektdateien wurden veraendert.
exit /b 1
