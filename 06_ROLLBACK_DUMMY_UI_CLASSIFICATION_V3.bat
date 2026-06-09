@echo off
setlocal
echo ========================================================================
echo Netzentgelt Dummy-UI-Klassifikation V3 - ROLLBACK
echo ========================================================================
.venv\Scripts\python.exe apply_dummy_ui_classification_v3.py rollback
if errorlevel 1 exit /b 1
echo.
echo OK.
exit /b 0
