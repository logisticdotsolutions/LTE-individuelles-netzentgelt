@echo off
echo ================================================================
echo Netzentgelt Cancelled Hotfix - VALIDATE
echo ================================================================
.venv\Scripts\python.exe validate_netzentgelt_cancelled_hotfix.py
if errorlevel 1 exit /b 1
