@echo off
setlocal
cd /d "%~dp0"
echo ========================================================================
echo Netzentgelt Phase 5E - REPOSITORY CLEANUP ROLLBACK
echo ========================================================================
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" cleanup_repository_phase5e.py rollback
) else (
    python cleanup_repository_phase5e.py rollback
)
if errorlevel 1 exit /b 1
echo.
echo OK: Entfernte Paketartefakte wurden wiederhergestellt.
