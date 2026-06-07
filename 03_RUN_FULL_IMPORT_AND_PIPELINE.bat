@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  set "PYTHON=.venv\Scripts\python.exe"
) else (
  set "PYTHON=python"
)
%PYTHON% scripts\download_blob_data.py
if errorlevel 1 goto :error
%PYTHON% scripts\run_all.py
if errorlevel 1 goto :error
echo.
echo Import und Pipeline erfolgreich abgeschlossen.
pause
exit /b 0
:error
echo.
echo FEHLER: Lauf wurde abgebrochen. Bitte Terminalausgabe pruefen.
pause
exit /b 1
