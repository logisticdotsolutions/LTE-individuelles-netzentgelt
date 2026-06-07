@echo off
setlocal
cd /d "%~dp0"
echo ================================================================
echo Netzentgelt Cancelled Hotfix V2 - STATIC + SMOKE VERIFY
echo ================================================================
if exist ".venv\Scripts\python.exe" (
    set "PYTHON=.venv\Scripts\python.exe"
) else (
    set "PYTHON=python"
)
"%PYTHON%" verify_cancelled_hotfix.py
if errorlevel 1 goto :error
echo.
echo VERIFIKATION erfolgreich.
exit /b 0
:error
echo.
echo FEHLER: Verifikation fehlgeschlagen.
exit /b 1
