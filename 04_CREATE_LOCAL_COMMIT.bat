@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_phase7b_pipeline_test_ui.ps1" -Mode Commit -TargetRoot "%CD%"
exit /b %ERRORLEVEL%
