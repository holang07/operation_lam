@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Tat ban dang chay cu o cong 8501 (neu co) de khong bi bao "Port 8501 is not available"
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8501 " ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>nul
rem ===== CHAY DU LIEU THAT, CO MAT KHAU, de chia se cho dong doi qua link =====
rem Mat khau: ghi 1 dong vao file team_password.txt (cung thu muc). Chua co file thi dung mat khau mac dinh duoi day.
if exist team_password.txt (
  set /p OMS_PASSWORD=<team_password.txt
) else (
  set /p OMS_PASSWORD=Chua co team_password.txt. Nhap mat khau de dung lan nay: 
)
python -m streamlit run app.py --server.port 8501 --server.headless true
pause
