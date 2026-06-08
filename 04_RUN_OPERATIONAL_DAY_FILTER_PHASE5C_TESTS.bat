@echo off
setlocal
cd /d "%~dp0"
echo ================================================================
echo Netzentgelt Operational Day Filter Phase 5C - LOGIKTESTS
echo ================================================================
.venv\Scripts\python.exe tests\test_operational_day_filter_phase5c.py
if errorlevel 1 exit /b 1
