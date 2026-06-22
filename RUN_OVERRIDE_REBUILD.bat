@echo off
setlocal

set PROJECT_ROOT=%~dp0
cd /d "%PROJECT_ROOT%"

echo ==============================================================================
echo Netzentgelt MVP - schneller Override-Rebuild
echo ==============================================================================
echo Projekt: %CD%
echo.

if not exist ".venv\Scripts\python.exe" (
    echo FEHLER: Python-Virtual-Environment nicht gefunden: .venv\Scripts\python.exe
    echo Bitte zuerst die Projektumgebung einrichten oder RUN_TESTS.bat pruefen.
    exit /b 1
)

".venv\Scripts\python.exe" scripts\run_pipeline.py --mode OVERRIDE_REBUILD
set EXIT_CODE=%ERRORLEVEL%

if not "%EXIT_CODE%"=="0" (
    echo.
    echo FEHLER: Override-Rebuild ist fehlgeschlagen. ExitCode=%EXIT_CODE%
    exit /b %EXIT_CODE%
)

echo.
echo Override-Rebuild abgeschlossen.
exit /b 0
