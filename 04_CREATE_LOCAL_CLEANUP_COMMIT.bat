@echo off
setlocal
set "PYTHON=python"
if exist "%CD%\.venv\Scripts\python.exe" set "PYTHON=%CD%\.venv\Scripts\python.exe"
"%PYTHON%" "%~dp0cleanup_netzentgelt_repository.py" --mode commit --target-root "%CD%"
exit /b %ERRORLEVEL%
