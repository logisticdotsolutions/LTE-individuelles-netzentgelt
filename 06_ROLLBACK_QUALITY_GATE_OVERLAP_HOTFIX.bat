@echo off
setlocal
cd /d "%~dp0"
echo ========================================================================
echo Netzentgelt Quality Gate Overlap Hotfix - ROLLBACK
echo ========================================================================
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" rollback_quality_gate_overlap_runtime.py
    ".venv\Scripts\python.exe" apply_netzentgelt_quality_gate_overlap_hotfix.py rollback
) else (
    python rollback_quality_gate_overlap_runtime.py
    python apply_netzentgelt_quality_gate_overlap_hotfix.py rollback
)
if errorlevel 1 exit /b 1
