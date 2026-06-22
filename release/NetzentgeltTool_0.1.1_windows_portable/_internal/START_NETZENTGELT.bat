@echo off
setlocal
cd /d %~dp0

echo ======================================================================
echo Netzentgelt Tool - Portable Start
echo ======================================================================
echo Ordner: %CD%
echo.

if exist NetzentgeltTool.exe (
  set APP_EXE=NetzentgeltTool.exe
) else if exist NetzentgeltMVP.exe (
  set APP_EXE=NetzentgeltMVP.exe
) else (
  echo FEHLER: Weder NetzentgeltTool.exe noch NetzentgeltMVP.exe wurde gefunden.
  echo Bitte pruefen, ob das ZIP vollstaendig entpackt wurde.
  echo.
  pause
  exit /b 2
)

echo Starte %APP_EXE% ...
"%APP_EXE%"
set EXITCODE=%ERRORLEVEL%

if not "%EXITCODE%"=="0" (
  echo.
  echo FEHLER: Das Tool wurde mit Exitcode %EXITCODE% beendet.
  echo Falls vorhanden, bitte diese Datei pruefen:
  echo %CD%\_portable_logs\launcher_error.log
  echo.
  pause
  exit /b %EXITCODE%
)

exit /b 0
