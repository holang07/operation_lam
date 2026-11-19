@echo off
chcp 65001 >nul
rem Tao link tam khac mang, KHONG can cai them gi (dung ssh co san trong Windows 10/11).
rem   share_demo.bat        -> chia se ban demo (cong 8502)
rem   share_demo.bat 8501   -> chia se ban du lieu that (chay run_team.bat truoc)
set PORT=%1
if "%PORT%"=="" set PORT=8502
echo Dang tao link cho cong %PORT%... Tim dong co chu https://...lhr.life roi gui cho ban.
echo Dong cua so nay la link het hieu luc.
echo.
ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=30 -R 80:localhost:%PORT% nokey@localhost.run
pause
