@echo off
setlocal
cd /d "%~dp0"

echo ================================================================
echo Netzentgelt Phase 2 - VOLLER IMPORT UND PIPELINE-LAUF
echo ================================================================

echo.
echo [1/3] Neue Rohdaten aus Azure Blob Storage laden ...
.venv\Scripts\python.exe scripts\download_blob_data.py
if errorlevel 1 (
    echo.
    echo FEHLER: Azure-Download ist fehlgeschlagen. Pipeline wird nicht gestartet.
    exit /b 1
)

echo.
echo [2/3] DuckDB, Findings, Quality Gate und Exporte neu berechnen ...
.venv\Scripts\python.exe scripts\run_all.py
if errorlevel 1 (
    echo.
    echo FEHLER: Pipeline-Lauf ist fehlgeschlagen.
    exit /b 1
)

echo.
echo [3/3] Phase-2-Tabellen validieren ...
.venv\Scripts\python.exe validate_netzentgelt_quality_gate_phase2.py
if errorlevel 1 (
    echo.
    echo FEHLER: Validierung ist fehlgeschlagen.
    exit /b 1
)

echo.
echo Vollstaendiger Phase-2-Lauf erfolgreich abgeschlossen.
endlocal
