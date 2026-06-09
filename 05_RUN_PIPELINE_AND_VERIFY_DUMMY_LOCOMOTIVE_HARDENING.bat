@echo off
setlocal
echo ========================================================================
echo Netzentgelt Dummy-Lokomotiven Hardening - PIPELINE UND VERIFIKATION
echo ========================================================================
.venv\Scripts\python.exe run_pipeline_verify_dummy_locomotive_hardening.py
if errorlevel 1 exit /b 1
echo.
echo OK.
exit /b 0
