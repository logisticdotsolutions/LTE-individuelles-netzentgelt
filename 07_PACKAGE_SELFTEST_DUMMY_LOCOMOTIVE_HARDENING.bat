@echo off
setlocal
echo ========================================================================
echo Netzentgelt Dummy-Lokomotiven Hardening
echo ========================================================================
.venv\Scripts\python.exe 07_PACKAGE_SELFTEST_DUMMY_LOCOMOTIVE_HARDENING.py
if errorlevel 1 exit /b 1
echo.
echo OK.
exit /b 0
