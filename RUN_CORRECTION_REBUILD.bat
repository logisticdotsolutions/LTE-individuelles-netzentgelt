@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo FEHLER: .venv\Scripts\python.exe nicht gefunden.
    exit /b 1
)

".venv\Scripts\python.exe" scripts\run_pipeline.py --mode CORRECTION_REBUILD
exit /b %ERRORLEVEL%
