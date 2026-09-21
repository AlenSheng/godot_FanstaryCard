@echo off
setlocal
cd /d "%~dp0"

set "EXIT_CODE=0"
set "COMPOSE_PROJECT_NAME=fantasycard-local"
set "NO_PAUSE="
set "CLOUD_DEPLOY="
set "PUSH_BEFORE_DEPLOY="
set "FORCE_NATIVE="

:args
if "%~1"=="" goto :start
if /I "%~1"=="--no-pause" (
    set "NO_PAUSE=1"
    shift
    goto :args
)
if /I "%~1"=="--native" (
    set "FORCE_NATIVE=1"
    shift
    goto :args
)
if /I "%~1"=="--cloud" (
    set "CLOUD_DEPLOY=1"
    shift
    goto :args
)
if /I "%~1"=="--push" (
    set "PUSH_BEFORE_DEPLOY=1"
    shift
    goto :args
)
echo Usage: update_server.bat [--native] [--cloud] [--push] [--no-pause]
set "EXIT_CODE=1"
goto :end

:start
if defined CLOUD_DEPLOY goto :cloud
if defined FORCE_NATIVE goto :native
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

:cloud
echo Starting the Tencent Cloud deployment flow...
if defined PUSH_BEFORE_DEPLOY (
    call "%CD%\cloud-update.bat" --push --no-pause
) else (
    call "%CD%\cloud-update.bat" --no-pause
)
set "EXIT_CODE=%ERRORLEVEL%"
goto :end

:native
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0local-server.ps1" -Action Build
set "EXIT_CODE=%ERRORLEVEL%"

:end
echo.
if not defined NO_PAUSE pause
exit /b %EXIT_CODE%
