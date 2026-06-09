@echo off
setlocal
echo ========================================================================
echo Netzentgelt Dummy-UI-Klassifikation - PIPELINE UND VERIFY
echo ========================================================================
.venv\Scripts\python.exe run_pipeline_verify_dummy_ui_classification_hotfix.py
if errorlevel 1 exit /b 1
echo.
echo OK.
exit /b 0
