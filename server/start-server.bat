@echo off
setlocal
cd /d "%~dp0"

set "EXIT_CODE=0"
set "COMPOSE_PROJECT_NAME=fantasycard-local"
set "NO_PAUSE="
if /I "%~1"=="--no-pause" set "NO_PAUSE=1"

echo [1/4] Checking Docker...
where docker >nul 2>nul
if errorlevel 1 (
    echo.
    echo [ERROR] Docker was not found. Install and start Docker Desktop first.
    set "EXIT_CODE=1"
    goto :end
)

set "COMPOSE_CMD=docker compose"
docker compose version >nul 2>nul
if errorlevel 1 (
    where docker-compose.exe >nul 2>nul
    if errorlevel 1 (
        echo.
        echo [ERROR] Docker Compose is unavailable. Update Docker Desktop first.
        set "EXIT_CODE=1"
        goto :end
    )
    set "COMPOSE_CMD=docker-compose.exe"
)

docker info >nul 2>nul
if errorlevel 1 (
    echo.
    echo [ERROR] Docker Desktop is not running. Start it and run this file again.
    set "EXIT_CODE=1"
    goto :end
)

echo [2/4] Downloading .NET base images (progress is shown below)...
docker pull mcr.microsoft.com/dotnet/sdk:10.0.400
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to download the .NET SDK base image.
    set "EXIT_CODE=1"
    goto :end
)
docker pull mcr.microsoft.com/dotnet/aspnet:10.0
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to download the .NET ASP.NET runtime base image.
    set "EXIT_CODE=1"
    goto :end
)

echo [3/4] Building and starting PostgreSQL and FantasyCard.Server...
%COMPOSE_CMD% up -d --build --remove-orphans
if errorlevel 1 (
    echo.
    echo [ERROR] Container build or startup failed.
    %COMPOSE_CMD% ps
    set "EXIT_CODE=1"
    goto :end
)

echo [4/4] Waiting for the server health check...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$deadline = (Get-Date).AddSeconds(60); while ((Get-Date) -lt $deadline) { try { $response = Invoke-WebRequest -UseBasicParsing -Uri 'http://localhost:5080/health/ready' -TimeoutSec 2; if ($response.StatusCode -eq 200) { exit 0 } } catch { }; Start-Sleep -Seconds 1 }; exit 1"
if errorlevel 1 (
    echo.
    echo [ERROR] The server did not become healthy within 60 seconds.
    echo Recent server logs:
    %COMPOSE_CMD% logs --tail 80 server
    set "EXIT_CODE=1"
    goto :end
)

echo.
echo [READY] FantasyCard local server is running.
echo         API:    http://localhost:5080
echo         Health: http://localhost:5080/health/ready
echo         Stop:   double-click stop-server.bat

:end
echo.
if not defined NO_PAUSE pause
exit /b %EXIT_CODE%
