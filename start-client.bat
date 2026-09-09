@echo off
setlocal
cd /d "%~dp0"
python tools\client_engine.py play
if errorlevel 1 pause
