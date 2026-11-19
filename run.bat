@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv (
  echo Dang cai dat lan dau, doi 1-2 phut...
  python -m venv .venv
  .venv\Scripts\python -m pip install --upgrade pip
  .venv\Scripts\python -m pip install -r requirements.txt
)
.venv\Scripts\python -m streamlit run app.py
pause
