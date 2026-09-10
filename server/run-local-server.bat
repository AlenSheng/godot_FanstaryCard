@echo off
setlocal
cd /d "%~dp0"
set "NO_PAUSE="
if /I "%~1"=="--no-pause" set "NO_PAUSE=1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0local-server.ps1" -Action Start
set "EXIT_CODE=%ERRORLEVEL%"
if not defined NO_PAUSE pause
exit /b %EXIT_CODE%
