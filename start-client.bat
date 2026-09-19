@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "NO_PAUSE="
rem Double-clicking this file is for the shared Tencent Cloud test server.
rem Use --local whenever you need the local Docker/.NET development service.
set "FANTASYCARD_SERVER_URL=https://www.relicbound.cn"

:args
if "%~1"=="" goto :start
if /I "%~1"=="--cloud" (
    set "FANTASYCARD_SERVER_URL=https://www.relicbound.cn"
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
echo [INFO] Connecting this client session to %FANTASYCARD_SERVER_URL%
rem Launch Godot directly.  The old Python launcher depended on the untracked
rem GameFactory-3A checkout and tools\engine-local manifest, neither of which
rem is present in a normal project checkout.
set "GODOT_EXECUTABLE=%A3GAME_GODOT_EXECUTABLE%"
if defined GODOT_EXECUTABLE if not exist "%GODOT_EXECUTABLE%" (
    echo [WARN] A3GAME_GODOT_EXECUTABLE does not exist: %GODOT_EXECUTABLE%
    set "GODOT_EXECUTABLE="
)
if not defined GODOT_EXECUTABLE if exist "%~dp0..\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64.exe" (
    set "GODOT_EXECUTABLE=%~dp0..\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64.exe"
)
if not defined GODOT_EXECUTABLE (
    echo [ERROR] Godot 4.7.2 was not found.
    echo [ERROR] Set A3GAME_GODOT_EXECUTABLE to your Godot executable, then try again.
    set "EXIT_CODE=1"
    goto :end
)
echo [INFO] Starting Godot: %GODOT_EXECUTABLE%
"%GODOT_EXECUTABLE%" --path "%~dp0client"
set "EXIT_CODE=%ERRORLEVEL%"
goto :end

:usage
echo Usage: start-client.bat [--cloud ^| --local ^| --url URL] [--no-pause]
set "EXIT_CODE=1"

:end
if not defined NO_PAUSE pause
exit /b %EXIT_CODE%
