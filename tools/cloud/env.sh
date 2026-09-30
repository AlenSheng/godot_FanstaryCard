#!/usr/bin/env bash
# Source this in each shell; setup-script exports do not persist in Codex Cloud.
export FANTASYCARD_CLOUD_TOOLS="${FANTASYCARD_CLOUD_TOOLS:-/opt/fantasycard-cloud-tools}"
export DOTNET_ROOT="$FANTASYCARD_CLOUD_TOOLS/dotnet"
export PATH="$FANTASYCARD_CLOUD_TOOLS/venv/bin:$DOTNET_ROOT:$FANTASYCARD_CLOUD_TOOLS/godot:$PATH"
export DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1
export NUGET_PACKAGES="$FANTASYCARD_CLOUD_TOOLS/nuget"
export FANTASYCARD_TEST_POSTGRES='Host=127.0.0.1;Port=55432;Username=postgres;Database=fantasycard_test'
