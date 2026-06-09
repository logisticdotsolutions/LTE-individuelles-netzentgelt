@echo off
setlocal
echo ========================================================================
echo Netzentgelt Dummy-UI-Klassifikation V3 - PACKAGE SELFTEST
echo ========================================================================
.venv\Scripts\python.exe package_selftest_dummy_ui_classification_v3.py
if errorlevel 1 exit /b 1
echo.
echo OK.
exit /b 0
