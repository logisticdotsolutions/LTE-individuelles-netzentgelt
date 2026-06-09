@echo off
setlocal
echo ========================================================================
echo Netzentgelt Dummy-Lokomotiven Hardening
echo ========================================================================
.venv\Scripts\python.exe apply_dummy_locomotive_hardening.py rollback
if errorlevel 1 exit /b 1
echo.
echo OK.
exit /b 0
