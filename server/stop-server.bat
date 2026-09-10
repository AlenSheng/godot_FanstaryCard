@echo off
setlocal
cd /d "%~dp0"

set "EXIT_CODE=0"
set "COMPOSE_PROJECT_NAME=fantasycard-local"
set "NO_PAUSE="
if /I "%~1"=="--no-pause" set "NO_PAUSE=1"

if exist "%~dp0.artifacts\local-server\state.json" goto :native
call "%~dp0docker-env.bat"
where docker >nul 2>nul
if errorlevel 1 (
    goto :native
)

set "COMPOSE_CMD=docker compose"
docker compose version >nul 2>nul
if errorlevel 1 (
    where docker-compose.exe >nul 2>nul
    if errorlevel 1 (
        echo [ERROR] Docker Compose is unavailable. The stop command cannot be executed.
        set "EXIT_CODE=1"
        goto :end
    )
    set "COMPOSE_CMD=docker-compose.exe"
)

echo Stopping FantasyCard.Server and PostgreSQL...
%COMPOSE_CMD% stop --timeout 15
if errorlevel 1 (
    echo.
    echo [ERROR] Stop failed. Make sure Docker Desktop is running.
    set "EXIT_CODE=1"
    goto :end
)

echo.
echo [STOPPED] Local services are stopped. PostgreSQL data is preserved.
echo           Double-click start-server.bat to start again.
goto :end

:native
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0local-server.ps1" -Action Stop
set "EXIT_CODE=%ERRORLEVEL%"

:end
echo.
if not defined NO_PAUSE pause
exit /b %EXIT_CODE%
