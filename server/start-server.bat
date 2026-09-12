@echo off
setlocal
cd /d "%~dp0"

set "EXIT_CODE=0"
set "COMPOSE_PROJECT_NAME=fantasycard-local"
set "NO_PAUSE="
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
echo Usage: start-server.bat [--native] [--no-pause]
set "EXIT_CODE=1"
goto :end

:start
echo [0/5] Checking published server/client config versions...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0assert-config-alignment.ps1"
if errorlevel 1 (
    echo.
    echo [ERROR] Published server/client config files are not aligned. Run tools\export-config.ps1 first.
    set "EXIT_CODE=1"
    goto :end
)
if defined FORCE_NATIVE goto :native
if exist "%~dp0.artifacts\local-server\state.json" goto :native
call "%~dp0docker-env.bat"

echo [1/5] Checking Docker...
where docker >nul 2>nul
if errorlevel 1 (
    echo [INFO] Docker was not found. Using local .NET and the configured PostgreSQL database.
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

echo [2/5] Checking .NET base images...
docker image inspect mcr.microsoft.com/dotnet/sdk:10.0.400 >nul 2>nul
if not errorlevel 1 goto :runtime_image
docker pull mcr.microsoft.com/dotnet/sdk:10.0.400
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to download the .NET SDK base image.
    set "EXIT_CODE=1"
    goto :end
)
:runtime_image
docker image inspect mcr.microsoft.com/dotnet/aspnet:10.0 >nul 2>nul
if not errorlevel 1 goto :build
docker pull mcr.microsoft.com/dotnet/aspnet:10.0
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to download the .NET ASP.NET runtime base image.
    set "EXIT_CODE=1"
    goto :end
)

:build
echo [3/5] Building and starting PostgreSQL and FantasyCard.Server...
%COMPOSE_CMD% up -d --build --remove-orphans
if errorlevel 1 (
    echo.
    echo [ERROR] Container build or startup failed.
    %COMPOSE_CMD% ps
    set "EXIT_CODE=1"
    goto :end
)

echo [4/5] Waiting for the server health check...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$deadline = (Get-Date).AddSeconds(60); while ((Get-Date) -lt $deadline) { try { $response = Invoke-WebRequest -UseBasicParsing -Uri 'http://localhost:5080/health/ready' -TimeoutSec 2; if ($response.StatusCode -eq 200) { exit 0 } } catch { }; Start-Sleep -Seconds 1 }; exit 1"
if errorlevel 1 (
    echo.
    echo [ERROR] The server did not become healthy within 60 seconds.
    echo Recent server logs:
    %COMPOSE_CMD% logs --tail 80 server
    set "EXIT_CODE=1"
    goto :end
)

echo [5/5] Checking that the running server matches the client config...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0assert-config-alignment.ps1" -RunningUrl "http://localhost:5080/"
if errorlevel 2 (
    echo.
    echo [ERROR] Published server/client config files are not aligned. Run tools\export-config.ps1 first.
    set "EXIT_CODE=1"
    goto :end
)
if errorlevel 1 (
    echo [UPDATE] Rebuilding the container so the running config matches this checkout...
    %COMPOSE_CMD% up -d --build --force-recreate --remove-orphans
    if errorlevel 1 (
        echo.
        echo [ERROR] Container rebuild failed after a config version mismatch.
        %COMPOSE_CMD% ps
        set "EXIT_CODE=1"
        goto :end
    )
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$deadline = (Get-Date).AddSeconds(60); while ((Get-Date) -lt $deadline) { try { $response = Invoke-WebRequest -UseBasicParsing -Uri 'http://localhost:5080/health/ready' -TimeoutSec 2; if ($response.StatusCode -eq 200) { exit 0 } } catch { }; Start-Sleep -Seconds 1 }; exit 1"
    if errorlevel 1 (
        echo.
        echo [ERROR] The rebuilt server did not become healthy within 60 seconds.
        echo Recent server logs:
        %COMPOSE_CMD% logs --tail 80 server
        set "EXIT_CODE=1"
        goto :end
    )
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0assert-config-alignment.ps1" -RunningUrl "http://localhost:5080/"
    if errorlevel 1 (
        echo.
        echo [ERROR] The running server config still does not match the client after rebuild.
        set "EXIT_CODE=1"
        goto :end
    )
)

echo.
echo [READY] FantasyCard local server is running.
echo         API:    http://localhost:5080
echo         Health: http://localhost:5080/health/ready
echo         Stop:   double-click stop-server.bat
goto :end

:native
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0local-server.ps1" -Action Start
set "EXIT_CODE=%ERRORLEVEL%"

:end
echo.
if not defined NO_PAUSE pause
exit /b %EXIT_CODE%
