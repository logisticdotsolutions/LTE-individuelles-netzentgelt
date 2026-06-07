@echo off
setlocal
cd /d "%~dp0"
echo ================================================================
echo Netzentgelt Phase 4 - Streamlit starten
echo ================================================================
.venv\Scripts\python.exe -m streamlit run app\app.py
