@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "CLOUD_SETTINGS_DIR=%CD%\"

set "NO_PAUSE="
if /I "%~1"=="--no-pause" set "NO_PAUSE=1"
if not "%~2"=="" goto :usage

if exist "%CLOUD_SETTINGS_DIR%cloud-env.local.bat" (
    call "%CLOUD_SETTINGS_DIR%cloud-env.local.bat"
    echo [INFO] Loaded cloud-env.local.bat.
) else (
    echo [INFO] cloud-env.local.bat was not found; using default connection settings.
)
if not defined FANTASYCARD_CLOUD_HOST set "FANTASYCARD_CLOUD_HOST=43.172.70.182"
if not defined FANTASYCARD_CLOUD_USER set "FANTASYCARD_CLOUD_USER=ubuntu"
if not defined FANTASYCARD_CLOUD_KEY set "FANTASYCARD_CLOUD_KEY=%USERPROFILE%\Downloads\gpt.pem"

if not exist "%FANTASYCARD_CLOUD_KEY%" (
    echo [ERROR] Cloud SSH key was not found: %FANTASYCARD_CLOUD_KEY%
    set "EXIT_CODE=1"
    goto :end
)

ssh -o BatchMode=yes -o ConnectTimeout=12 -i "%FANTASYCARD_CLOUD_KEY%" %FANTASYCARD_CLOUD_USER%@%FANTASYCARD_CLOUD_HOST% "printf 'Deployed commit: '; cat /opt/fantasycard-app/deployed-git-commit; if test -f /opt/fantasycard-app/version-manifests/release.version; then printf 'Manifest version: '; cat /opt/fantasycard-app/version-manifests/release.version; printf 'Tracked server files: '; wc -l /opt/fantasycard-app/version-manifests/release.md5; fi; curl --fail --silent --show-error --max-time 5 -o /dev/null http://127.0.0.1:8080/health/ready && curl --fail --silent --show-error --max-time 5 -o /dev/null --resolve www.relicbound.cn:443:127.0.0.1 https://www.relicbound.cn/health/ready && echo HEALTHY"
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" echo [ERROR] Cloud health check failed.
goto :end

:usage
echo Usage: cloud-status.bat [--no-pause]
set "EXIT_CODE=1"

:end
echo.
if not defined NO_PAUSE pause
exit /b %EXIT_CODE%
