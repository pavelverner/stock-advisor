@echo off
cd /d "%~dp0"
echo Spouštím Stock Advisor Dashboard...
python -m streamlit run app.py --browser.gatherUsageStats false --server.port 8501
pause
