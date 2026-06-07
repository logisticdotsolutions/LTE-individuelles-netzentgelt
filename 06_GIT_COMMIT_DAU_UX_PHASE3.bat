@echo off
setlocal
cd /d "%~dp0"
echo ================================================================
echo Netzentgelt Phase 3 - GIT COMMIT
echo ================================================================
git add app\app.py scripts\operator_ui_module.py
git commit -m "Add DAU-friendly operator UI for quality gate workflow"
if errorlevel 1 (
  echo.
  echo HINWEIS: Commit konnte nicht erstellt werden. Bitte git status pruefen.
  exit /b 1
)
echo.
echo OK: Commit wurde erstellt. Fuer GitHub anschliessend git push ausfuehren.
