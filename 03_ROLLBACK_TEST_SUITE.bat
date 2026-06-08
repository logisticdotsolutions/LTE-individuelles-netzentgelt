@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_testsuite.ps1" -Mode Rollback -TargetRoot "%CD%"
exit /b %ERRORLEVEL%
