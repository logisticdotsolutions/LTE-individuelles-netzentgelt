@echo off
setlocal
echo ========================================================================
echo Netzentgelt Phase6C Adjacency Hotfix
echo ========================================================================
.venv\Scripts\python.exe run_pipeline_verify_phase6c_adjacency_hotfix.py
if errorlevel 1 exit /b 1
echo.
echo OK.
exit /b 0
