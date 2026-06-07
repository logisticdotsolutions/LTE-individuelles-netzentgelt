@echo off
setlocal
cd /d "%~dp0"
echo ================================================================
echo Netzentgelt Phase 3 - STREAMLIT STARTEN
echo ================================================================
.venv\Scripts\python.exe -m streamlit run app\app.py
