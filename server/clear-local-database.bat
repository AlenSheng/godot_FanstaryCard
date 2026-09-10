@echo off
setlocal
cd /d "%~dp0"
call "%~dp0docker-env.bat"

set "EXIT_CODE=0"
set "COMPOSE_PROJECT_NAME=fantasycard-local"
set "AUTO_CONFIRM="
set "NO_PAUSE="

:parse_args
if "%~1"=="" goto :args_done
if /I "%~1"=="--yes" (
    set "AUTO_CONFIRM=1"
) else if /I "%~1"=="--no-pause" (
    set "NO_PAUSE=1"
) else if /I "%~1"=="--help" (
    set "NO_PAUSE=1"
    goto :help
) else (
    echo [ERROR] Unknown option: %~1
    set "EXIT_CODE=2"
    goto :end
)
shift
goto :parse_args

:args_done
echo [WARNING] This will permanently delete all FantasyCard local PostgreSQL data.
echo           Docker project: %COMPOSE_PROJECT_NAME%
echo           The database will be recreated and all migrations will be applied.
echo.

if not defined AUTO_CONFIRM (
    choice /C YN /N /M "Continue? [Y/N] "
    if errorlevel 2 goto :cancelled
)

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

echo [2/4] Stopping local services...
%COMPOSE_CMD% down --remove-orphans
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to stop the local Docker services.
    set "EXIT_CODE=1"
    goto :end
)

echo [3/4] Removing the local PostgreSQL data volume...
docker volume rm "%COMPOSE_PROJECT_NAME%_fantasycard-postgres" >nul 2>nul
if errorlevel 1 (
    docker volume inspect "%COMPOSE_PROJECT_NAME%_fantasycard-postgres" >nul 2>nul
    if not errorlevel 1 (
        echo.
        echo [ERROR] The local PostgreSQL volume could not be removed.
        set "EXIT_CODE=1"
        goto :end
    )
    echo         No existing local PostgreSQL volume was found; creating a new one.
)

echo [4/4] Recreating the database and applying migrations...
call "%~dp0start-server.bat" --no-pause
if errorlevel 1 (
    echo.
    echo [ERROR] The local database rebuild could not be completed.
    set "EXIT_CODE=1"
    goto :end
)

echo.
echo [DONE] FantasyCard local PostgreSQL data was cleared and rebuilt.
goto :end

:cancelled
echo.
echo [CANCELLED] No local database data was changed.
goto :end

:help
echo Usage: clear-local-database.bat [--yes] [--no-pause]
echo.
echo   --yes       Skip the destructive-action confirmation.
echo   --no-pause  Exit without waiting for a key press.
goto :end

:end
echo.
if not defined NO_PAUSE pause
exit /b %EXIT_CODE%
