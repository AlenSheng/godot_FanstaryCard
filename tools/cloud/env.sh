#!/usr/bin/env bash
# Source for each shell; install-script exports are not persistent.
export FANTASYCARD_CLOUD_TOOLS="${FANTASYCARD_CLOUD_TOOLS:-/workspace/fantasycard-cloud-tools}"
if [[ -x "$FANTASYCARD_CLOUD_TOOLS/dotnet/usr/share/dotnet/dotnet" ]]; then
  export DOTNET_ROOT="$FANTASYCARD_CLOUD_TOOLS/dotnet/usr/share/dotnet"
else
  export DOTNET_ROOT="$FANTASYCARD_CLOUD_TOOLS/dotnet"
fi
export PATH="$FANTASYCARD_CLOUD_TOOLS/venv/bin:$DOTNET_ROOT:$FANTASYCARD_CLOUD_TOOLS/godot:$FANTASYCARD_CLOUD_TOOLS/postgres/bin:$PATH"
export DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1
export DOTNET_CLI_HOME="$FANTASYCARD_CLOUD_TOOLS/dotnet-home"
export NUGET_PACKAGES="${FANTASYCARD_CLOUD_NUGET_CACHE:-$FANTASYCARD_CLOUD_TOOLS/nuget}"
export FANTASYCARD_TEST_POSTGRES="Host=$FANTASYCARD_CLOUD_TOOLS/postgres-test/socket;Port=55432;Username=postgres;Database=fantasycard_test"
export XDG_CACHE_HOME="$FANTASYCARD_CLOUD_TOOLS/client/cache"
export XDG_CONFIG_HOME="$FANTASYCARD_CLOUD_TOOLS/client/config"
export XDG_DATA_HOME="$FANTASYCARD_CLOUD_TOOLS/client/data"
