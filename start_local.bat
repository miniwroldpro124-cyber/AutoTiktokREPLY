@echo off
rem TikTok Auto Reply - shortcut local (worker + panel localhost)
rem Goi: start_local.bat          -> chi bat 2 dich vu (tu auto-start)
rem       start_local.bat open     -> bat + mo panel tren trinh duyet
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_local.ps1" %*
exit /b %errorlevel%
