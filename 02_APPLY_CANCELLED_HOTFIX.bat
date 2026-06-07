@echo off
setlocal
cd /d "%~dp0"
echo ================================================================
echo Netzentgelt Cancelled Hotfix V2 - APPLY
echo ================================================================
if exist ".venv\Scripts\python.exe" (
    set "PYTHON=.venv\Scripts\python.exe"
) else (
    set "PYTHON=python"
)
"%PYTHON%" apply_netzentgelt_cancelled_hotfix.py --dry-run
if errorlevel 1 goto :error
"%PYTHON%" apply_netzentgelt_cancelled_hotfix.py --apply
if errorlevel 1 goto :error
echo.
echo APPLY erfolgreich. Automatisches Backup wurde erstellt.
exit /b 0
:error
echo.
echo FEHLER: Hotfix wurde nicht angewendet oder automatisch zurueckgerollt.
exit /b 1
