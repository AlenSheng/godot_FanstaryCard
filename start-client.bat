@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "NO_PAUSE="
set "FANTASYCARD_SERVER_URL="

:args
if "%~1"=="" goto :start
if /I "%~1"=="--cloud" (
    set "FANTASYCARD_SERVER_URL=http://43.172.70.182"
    shift
    goto :args
)
if /I "%~1"=="--local" (
    set "FANTASYCARD_SERVER_URL=http://127.0.0.1:5080"
    shift
    goto :args
)
if /I "%~1"=="--url" (
    if "%~2"=="" goto :usage
    set "FANTASYCARD_SERVER_URL=%~2"
    shift
    shift
    goto :args
)
if /I "%~1"=="--no-pause" (
    set "NO_PAUSE=1"
    shift
    goto :args
)
goto :usage

:start
if defined FANTASYCARD_SERVER_URL (
    echo [INFO] Connecting this client session to %FANTASYCARD_SERVER_URL%
) else (
    echo [INFO] Using the client saved server address.
)
python tools\client_engine.py play
set "EXIT_CODE=%ERRORLEVEL%"
goto :end

:usage
echo Usage: start-client.bat [--cloud ^| --local ^| --url URL] [--no-pause]
set "EXIT_CODE=1"

:end
if not defined NO_PAUSE pause
exit /b %EXIT_CODE%
