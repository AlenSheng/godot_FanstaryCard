@echo off
setlocal EnableExtensions
cd /d "%~dp0.."
set "CLOUD_SETTINGS_DIR=%CD%\server\"
set "PUBLISH_BRANCH=release"

set "EXIT_CODE=0"
set "NO_PAUSE="
set "PUSH_BEFORE_DEPLOY="

:args
if "%~1"=="" goto :settings
if /I "%~1"=="--no-pause" (
    set "NO_PAUSE=1"
    shift
    goto :args
)
if /I "%~1"=="--push" (
    set "PUSH_BEFORE_DEPLOY=1"
    shift
    goto :args
)
echo Usage: cloud-update.bat [--push] [--no-pause]
set "EXIT_CODE=1"
goto :end

:settings
if exist "%CLOUD_SETTINGS_DIR%cloud-env.local.bat" (
    call "%CLOUD_SETTINGS_DIR%cloud-env.local.bat"
    echo [INFO] Loaded cloud-env.local.bat.
) else (
    echo [INFO] cloud-env.local.bat was not found; using default connection settings.
)
if not defined FANTASYCARD_CLOUD_HOST set "FANTASYCARD_CLOUD_HOST=43.172.70.182"
if not defined FANTASYCARD_CLOUD_USER set "FANTASYCARD_CLOUD_USER=ubuntu"
if not defined FANTASYCARD_CLOUD_KEY set "FANTASYCARD_CLOUD_KEY=%USERPROFILE%\Downloads\gpt.pem"
if not defined FANTASYCARD_CLOUD_UPDATE_COMMAND set "FANTASYCARD_CLOUD_UPDATE_COMMAND=~/fantasycard-update"

if not exist "%FANTASYCARD_CLOUD_KEY%" (
    echo [ERROR] Cloud SSH key was not found:
    echo         %FANTASYCARD_CLOUD_KEY%
    echo         Copy cloud-env.example.bat to cloud-env.local.bat and set FANTASYCARD_CLOUD_KEY.
    set "EXIT_CODE=1"
    goto :end
)

where ssh >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Windows OpenSSH client was not found.
    set "EXIT_CODE=1"
    goto :end
)

for /f "usebackq delims=" %%B in (`git branch --show-current`) do set "CURRENT_BRANCH=%%B"
if /I not "%CURRENT_BRANCH%"=="%PUBLISH_BRANCH%" (
    echo [ERROR] Cloud deployment only accepts the %PUBLISH_BRANCH% branch. Current branch: %CURRENT_BRANCH%
    echo         Switch to %PUBLISH_BRANCH% before deploying.
    set "EXIT_CODE=1"
    goto :end
)

if defined PUSH_BEFORE_DEPLOY (
    echo [1/2] Pushing committed changes to GitHub...
    git status --short
    git push origin %PUBLISH_BRANCH%
    if errorlevel 1 (
        echo [ERROR] GitHub push failed. Cloud deployment was not started.
        set "EXIT_CODE=1"
        goto :end
    )
) else (
    echo [1/2] Using the latest code already pushed to GitHub...
)

echo [2/2] Updating Tencent Cloud server...
ssh -o BatchMode=yes -o ConnectTimeout=12 -i "%FANTASYCARD_CLOUD_KEY%" %FANTASYCARD_CLOUD_USER%@%FANTASYCARD_CLOUD_HOST% "%FANTASYCARD_CLOUD_UPDATE_COMMAND%"
if errorlevel 1 (
    echo [ERROR] Cloud update failed. The server script keeps its database backup and prints the cause above.
    set "EXIT_CODE=1"
    goto :end
)

echo.
echo [UPDATED] Tencent Cloud server deployment completed successfully.

:end
echo.
if not defined NO_PAUSE pause
exit /b %EXIT_CODE%
