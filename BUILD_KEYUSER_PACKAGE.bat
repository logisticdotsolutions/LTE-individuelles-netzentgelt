@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0BUILD_WINDOWS_EXE.ps1" %*
exit /b %ERRORLEVEL%
