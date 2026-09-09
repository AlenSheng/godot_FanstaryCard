@echo off
setlocal
cd /d "%~dp0"
set "ASPNETCORE_ENVIRONMENT=Development"
set "ASPNETCORE_URLS=http://127.0.0.1:5080"
dotnet run --project src/FantasyCard.Server --no-build
