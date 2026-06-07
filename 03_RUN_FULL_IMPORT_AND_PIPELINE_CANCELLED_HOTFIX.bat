@echo off
echo ================================================================
echo Netzentgelt Cancelled Hotfix - FULL IMPORT AND PIPELINE
echo ================================================================
.venv\Scripts\python.exe scripts\download_blob_data.py
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe scripts\run_all.py
if errorlevel 1 exit /b 1
