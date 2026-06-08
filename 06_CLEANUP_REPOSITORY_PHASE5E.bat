@echo off
setlocal
cd /d "%~dp0"
echo ========================================================================
echo Netzentgelt Phase 5E - REPOSITORY CLEANUP
echo ========================================================================
echo Zuerst wird nur angezeigt, welche alten Paketartefakte entfernt werden.
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" cleanup_repository_phase5e.py dry-run
) else (
    python cleanup_repository_phase5e.py dry-run
)
if errorlevel 1 exit /b 1
echo.
set /p CONFIRM=Bereinigung jetzt anwenden? Bitte JA eingeben: 
if /I not "%CONFIRM%"=="JA" (
    echo Abgebrochen. Keine Dateien wurden entfernt.
    exit /b 0
)
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" cleanup_repository_phase5e.py apply
) else (
    python cleanup_repository_phase5e.py apply
)
if errorlevel 1 exit /b 1
echo.
echo OK: Alte Paketartefakte wurden lokal entfernt.
