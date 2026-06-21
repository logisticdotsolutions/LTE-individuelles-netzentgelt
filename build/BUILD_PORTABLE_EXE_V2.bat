@echo off
setlocal
cd /d %~dp0..

if not exist .venv\Scripts\python.exe (
  echo FEHLER: .venv wurde nicht gefunden. Bitte zuerst lokale Entwicklungsumgebung erstellen.
  exit /b 2
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller

if not exist config\portable_runtime.enc (
  echo FEHLER: config\portable_runtime.enc fehlt.
  echo Beispiel: python tools\write_portable_config.py --input config\portable_runtime.private.json
  exit /b 3
)

if not exist config\portable_runtime.key (
  echo FEHLER: config\portable_runtime.key fehlt.
  exit /b 4
)

pyinstaller --clean --noconfirm build\NetzentgeltToolPortable.spec
if errorlevel 1 exit /b %errorlevel%

echo.
echo OK: Portable EXE wurde erstellt: dist\NetzentgeltTool\NetzentgeltTool.exe
exit /b 0
