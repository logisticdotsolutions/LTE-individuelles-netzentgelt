@echo off
setlocal
cd /d "%~dp0"
echo ================================================================
echo Netzentgelt Operational Day Filter Phase 5C - VERIFY
echo ================================================================
.venv\Scripts\python.exe apply_operational_day_filter_phase5c.py verify --project-root .
if errorlevel 1 exit /b 1
