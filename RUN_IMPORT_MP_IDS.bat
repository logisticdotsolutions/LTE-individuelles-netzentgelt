@echo off
setlocal
set ROOT=%~dp0
if exist "%ROOT%.venv\Scripts\python.exe" (
  set PYTHON=%ROOT%.venv\Scripts\python.exe
) else (
  set PYTHON=python
)

%PYTHON% "%ROOT%scripts\import_market_partner_ids.py"
exit /b %ERRORLEVEL%
