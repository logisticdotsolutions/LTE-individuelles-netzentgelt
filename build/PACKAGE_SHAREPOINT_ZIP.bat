@echo off
setlocal
cd /d %~dp0..

if "%1"=="" (
  set VERSION=dev
) else (
  set VERSION=%1
)

if not exist dist\NetzentgeltTool\NetzentgeltTool.exe (
  echo FEHLER: dist\NetzentgeltTool\NetzentgeltTool.exe fehlt.
  echo Bitte zuerst build\BUILD_PORTABLE_EXE.bat ausführen.
  exit /b 2
)

if not exist release mkdir release
set ZIP_PATH=release\NetzentgeltTool_%VERSION%_windows_portable.zip
if exist "%ZIP_PATH%" del "%ZIP_PATH%"

powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path 'dist\NetzentgeltTool\*' -DestinationPath '%ZIP_PATH%' -Force"
if errorlevel 1 exit /b %errorlevel%

echo.
echo OK: SharePoint-Paket erstellt: %ZIP_PATH%
echo Dieses ZIP kann auf SharePoint hochgeladen werden.
exit /b 0
