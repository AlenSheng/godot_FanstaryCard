@echo off
setlocal
cd /d "%~dp0"

set "EXIT_CODE=0"
set "COMPOSE_PROJECT_NAME=fantasycard-local"
set "NO_PAUSE="
if /I "%~1"=="--no-pause" set "NO_PAUSE=1"
if /I "%~2"=="--no-pause" set "NO_PAUSE=1"
if /I "%~1"=="--native" goto :native
if /I "%~2"=="--native" goto :native
if exist "%~dp0.artifacts\local-server\state.json" goto :native
call "%~dp0docker-env.bat"

echo [1/2] Checking Docker...
where docker >nul 2>nul
if errorlevel 1 (
    goto :native
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

echo [2/2] Rebuilding the FantasyCard.Server image...
%COMPOSE_CMD% build server
if errorlevel 1 (
    echo.
    echo [ERROR] FantasyCard.Server image build failed.
    set "EXIT_CODE=1"
    goto :end
)

echo.
echo [UPDATED] FantasyCard.Server image was rebuilt successfully.
echo           Run start-server.bat when you want to start the Docker services.
goto :end

:native
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0local-server.ps1" -Action Build
set "EXIT_CODE=%ERRORLEVEL%"

:end
echo.
if not defined NO_PAUSE pause
exit /b %EXIT_CODE%
