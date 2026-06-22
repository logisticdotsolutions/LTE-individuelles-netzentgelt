@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" scripts\run_pipeline.py --mode CORRECTION_REBUILD
exit /b %ERRORLEVEL%
