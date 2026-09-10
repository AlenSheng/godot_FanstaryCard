@echo off
setlocal
cd /d "%~dp0"
call "%~dp0docker-env.bat"

set "EXIT_CODE=0"
set "COMPOSE_PROJECT_NAME=fantasycard-local"
set "NO_PAUSE="

:parse_args
if "%~1"=="" goto :args_done
if /I "%~1"=="--no-pause" (
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
echo [1/6] Checking Docker and the local database volume...
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

docker volume inspect "%COMPOSE_PROJECT_NAME%_fantasycard-postgres" >nul 2>nul
if errorlevel 1 (
    echo.
    echo [ERROR] No FantasyCard local PostgreSQL data volume was found.
    echo         Run start-server.bat successfully before creating a backup.
    set "EXIT_CODE=1"
    goto :end
)

echo [2/6] Starting PostgreSQL if needed...
set "POSTGRES_CONTAINER="
for /f "delims=" %%I in ('%COMPOSE_CMD% ps --all -q postgres') do set "POSTGRES_CONTAINER=%%I"
if defined POSTGRES_CONTAINER (
    %COMPOSE_CMD% start postgres
) else (
    %COMPOSE_CMD% up -d postgres
)
if errorlevel 1 (
    echo.
    echo [ERROR] PostgreSQL could not be started.
    set "EXIT_CODE=1"
    goto :end
)

for /L %%I in (1,1,30) do (
    %COMPOSE_CMD% exec -T postgres pg_isready -U fantasycard -d fantasycard >nul 2>nul
    if not errorlevel 1 goto :database_ready
    timeout /t 2 /nobreak >nul
)

echo.
echo [ERROR] PostgreSQL did not become ready within 60 seconds.
set "EXIT_CODE=1"
goto :end

:database_ready
echo [3/6] Verifying the FantasyCard schema...
set "SCHEMA_STATUS="
for /f "delims=" %%I in ('%COMPOSE_CMD% exec -T postgres psql -U fantasycard -d fantasycard -Atc "SELECT CASE WHEN to_regclass($$public.players$$) IS NOT NULL AND to_regclass($$public.schema_migrations$$) IS NOT NULL THEN $$ready$$ ELSE $$missing$$ END;"') do set "SCHEMA_STATUS=%%I"
if /I not "%SCHEMA_STATUS%"=="ready" (
    echo.
    echo [ERROR] The database is reachable, but the FantasyCard schema is missing.
    echo         Run start-server.bat successfully so migrations can be applied.
    set "EXIT_CODE=1"
    goto :end
)

for /f "delims=" %%I in ('powershell.exe -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"') do set "BACKUP_TIMESTAMP=%%I"
set "BACKUP_DIR=%~dp0local-backups"
set "BACKUP_NAME=fantasycard-local_%BACKUP_TIMESTAMP%.dump"
set "BACKUP_FILE=%BACKUP_DIR%\%BACKUP_NAME%"
set "CHECKSUM_FILE=%BACKUP_FILE%.sha256"
set "CONTAINER_BACKUP=/tmp/%BACKUP_NAME%"

if not exist "%BACKUP_DIR%" mkdir "%BACKUP_DIR%"
if errorlevel 1 (
    echo.
    echo [ERROR] Could not create the backup directory: %BACKUP_DIR%
    set "EXIT_CODE=1"
    goto :end
)

echo [4/6] Creating a consistent full-database dump...
%COMPOSE_CMD% exec -T postgres pg_dump -U fantasycard -d fantasycard --format=custom --compress=9 --no-owner --no-privileges --file="%CONTAINER_BACKUP%"
if errorlevel 1 (
    echo.
    echo [ERROR] pg_dump failed.
    set "EXIT_CODE=1"
    goto :cleanup_container
)

%COMPOSE_CMD% exec -T postgres pg_restore --list "%CONTAINER_BACKUP%" >nul
if errorlevel 1 (
    echo.
    echo [ERROR] PostgreSQL could not validate the generated dump.
    set "EXIT_CODE=1"
    goto :cleanup_container
)

echo [5/6] Copying the dump into the Git working directory...
if not defined POSTGRES_CONTAINER (
    echo.
    echo [ERROR] The PostgreSQL container ID could not be resolved.
    set "EXIT_CODE=1"
    goto :cleanup_container
)

docker cp "%POSTGRES_CONTAINER%:%CONTAINER_BACKUP%" "%BACKUP_FILE%"
if errorlevel 1 (
    echo.
    echo [ERROR] The database dump could not be copied to: %BACKUP_FILE%
    set "EXIT_CODE=1"
    goto :cleanup_container
)

for %%I in ("%BACKUP_FILE%") do if %%~zI LEQ 0 (
    echo.
    echo [ERROR] The copied database dump is empty.
    set "EXIT_CODE=1"
    goto :cleanup_host
)

echo [6/6] Writing the SHA-256 checksum...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "try { $stream = [System.IO.File]::OpenRead('%BACKUP_FILE%'); $sha = [System.Security.Cryptography.SHA256]::Create(); try { $hash = [System.BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() } finally { $sha.Dispose(); $stream.Dispose() }; [System.IO.File]::WriteAllText('%CHECKSUM_FILE%', $hash + '  %BACKUP_NAME%' + [Environment]::NewLine, [System.Text.Encoding]::ASCII); exit 0 } catch { Write-Error $_; exit 1 }"
if errorlevel 1 (
    echo.
    echo [ERROR] The checksum file could not be created.
    set "EXIT_CODE=1"
    goto :cleanup_host
)

%COMPOSE_CMD% exec -T postgres rm -f "%CONTAINER_BACKUP%" >nul 2>nul
echo.
echo [DONE] All FantasyCard local PostgreSQL data was backed up.
echo        Dump:     %BACKUP_FILE%
echo        Checksum: %CHECKSUM_FILE%
echo        Copy both files to the other device for migration.
goto :end

:cleanup_host
if exist "%BACKUP_FILE%" del /Q "%BACKUP_FILE%" >nul 2>nul
if exist "%CHECKSUM_FILE%" del /Q "%CHECKSUM_FILE%" >nul 2>nul

:cleanup_container
%COMPOSE_CMD% exec -T postgres rm -f "%CONTAINER_BACKUP%" >nul 2>nul
goto :end

:help
echo Usage: backup-all-local-data.bat [--no-pause]
echo.
echo Creates a complete PostgreSQL dump and SHA-256 checksum under:
echo   server\local-backups\
goto :end

:end
echo.
if not defined NO_PAUSE pause
exit /b %EXIT_CODE%
