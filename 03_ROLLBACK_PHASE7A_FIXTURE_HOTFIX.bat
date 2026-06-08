@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_phase7a_fixture_hotfix.ps1" -Mode Rollback -TargetRoot "%CD%"
exit /b %ERRORLEVEL%
