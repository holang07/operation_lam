@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Tat ban dang chay cu o cong 8502 (neu co) de khong bi bao "Port 8502 is not available"
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8502 " ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>nul
rem ===== BAN DEMO: du lieu gia, co mat khau =====
set OMS_DB=%~dp0demo_data\workspace.db
set OMS_PASSWORD=demo2026
if not exist demo_data\workspace.db python make_demo.py
python -m streamlit run app.py --server.port 8502 --server.headless true
pause
