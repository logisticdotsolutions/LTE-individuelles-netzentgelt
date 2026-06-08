@echo off
setlocal
cd /d "%~dp0"
echo ========================================================================
echo Netzentgelt Quality Gate Overlap Hotfix - RUN PIPELINE AND VERIFY DATA
echo ========================================================================
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" run_pipeline_and_verify_quality_gate_overlap.py
) else (
    python run_pipeline_and_verify_quality_gate_overlap.py
)
if errorlevel 1 exit /b 1
