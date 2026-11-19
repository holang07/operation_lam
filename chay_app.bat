@echo off
chcp 65001 >nul
title Operation Management System
cd /d "%~dp0"
rem Tat ban cu o cong 8501 (neu co)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8501 " ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>nul
if exist team_password.txt (
  set /p OMS_PASSWORD=<team_password.txt
) else (
  set /p OMS_PASSWORD=Chua co team_password.txt. Nhap mat khau de dung lan nay: 
)
rem Mo trinh duyet sau 4 giay
start "" /b cmd /c "timeout /t 4 /nobreak >nul & start http://localhost:8501"
python -m streamlit run app.py --server.port 8501 --server.headless true
pause
