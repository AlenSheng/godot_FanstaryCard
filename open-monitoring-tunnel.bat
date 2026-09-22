@echo off
setlocal
title FantasyCard Monitoring SSH Tunnel

set "SSH_KEY=F:\个人文件夹\gpt.pem"
set "SSH_TARGET=ubuntu@43.172.70.182"
set "GRAFANA_URL=http://localhost:3000/d/fantasycard-cloud"

where ssh >nul 2>&1
if errorlevel 1 (
    echo OpenSSH was not found. Install Windows OpenSSH Client first.
    pause
    exit /b 1
)

if not exist "%SSH_KEY%" (
    echo SSH key not found: %SSH_KEY%
    pause
    exit /b 1
)

echo Starting SSH tunnel...
echo Grafana:    http://localhost:3000
echo Prometheus: http://localhost:9090
echo Close the SSH window to stop the tunnel.

start "FantasyCard Monitoring SSH Tunnel" cmd /k ssh ^
  -o ExitOnForwardFailure=yes ^
  -o ConnectTimeout=10 ^
  -o ServerAliveInterval=30 ^
  -o ServerAliveCountMax=3 ^
  -o StrictHostKeyChecking=accept-new ^
  -i "%SSH_KEY%" ^
  -N ^
  -L 3000:127.0.0.1:3000 ^
  -L 9090:127.0.0.1:9090 ^
  %SSH_TARGET%

timeout /t 3 /nobreak >nul
start "" "%GRAFANA_URL%"
exit /b 0
