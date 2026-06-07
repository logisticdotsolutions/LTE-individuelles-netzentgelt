@echo off
setlocal
cd /d "%~dp0"
echo ================================================================
echo Netzentgelt Phase 4 - Git Commit
echo ================================================================
git add app\app.py scripts\rest_export_module.py
git commit -m "Simplify exports to LTE DE, LTE NL and Rest overview"
echo.
echo Danach ausfuehren: git push
