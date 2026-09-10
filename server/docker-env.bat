@echo off
rem Add Docker Desktop to this shell only; per-user installs may not update PATH.
where docker >nul 2>nul
if not errorlevel 1 exit /b 0
for %%D in ("%LOCALAPPDATA%\Programs\DockerDesktop\resources\bin" "%ProgramFiles%\Docker\Docker\resources\bin" "%LOCALAPPDATA%\Programs\Docker\Docker\resources\bin") do (
    if exist "%%~D\docker.exe" (
        set "PATH=%%~D;%PATH%"
        exit /b 0
    )
)
exit /b 1
