@echo off
setlocal
echo ========================================================================
echo Netzentgelt Dummy-Lokomotiven Verify-Schema-Hotfix - ROLLBACK
echo ========================================================================
.venv\Scripts\python.exe apply_dummy_locomotive_verify_schema_hotfix.py rollback
if errorlevel 1 exit /b 1
echo.
echo OK.
exit /b 0
