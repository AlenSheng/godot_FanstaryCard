#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
source tools/cloud/env.sh
[[ $(id -u) != 0 ]] || { echo 'Private test database requires an unprivileged user' >&2; exit 1; }
pg_bin="$FANTASYCARD_CLOUD_TOOLS/postgres/bin"
pg_root="$FANTASYCARD_CLOUD_TOOLS/postgres-test"
[[ $FANTASYCARD_CLOUD_TOOLS = /* && $FANTASYCARD_CLOUD_TOOLS != *[[:space:]]* && ${#pg_root} -le 75 ]] || { echo 'Use a short absolute tools path without whitespace' >&2; exit 1; }
mkdir -p "$pg_root/socket"
chmod 700 "$pg_root" "$pg_root/socket"
exec 8>"$pg_root/start.lock"
flock -x 8
if [[ ! -f "$pg_root/data/PG_VERSION" ]]; then
  "$pg_bin/initdb" -D "$pg_root/data" -U postgres --auth-local=trust --auth-host=reject --no-locale --encoding=UTF8 >/dev/null
fi
[[ $(cat "$pg_root/data/PG_VERSION") == 18 ]]
if ! "$pg_bin/pg_ctl" -D "$pg_root/data" status >/dev/null 2>&1; then
  "$pg_bin/pg_ctl" -D "$pg_root/data" -l "$pg_root/postgres.log" -o "-h '' -p 55432 -k $pg_root/socket -c unix_socket_permissions=0700" -w start >/dev/null 8>&-
fi
[[ $("$pg_bin/psql" -h "$pg_root/socket" -p 55432 -U postgres -d postgres -Atc 'SHOW listen_addresses') == '' ]]
"$pg_bin/pg_isready" -h "$pg_root/socket" -p 55432 -U postgres
if ! "$pg_bin/psql" -h "$pg_root/socket" -p 55432 -U postgres -d postgres -Atc "SELECT 1 FROM pg_database WHERE datname='fantasycard_test'" | rg -qx 1; then
  "$pg_bin/createdb" -h "$pg_root/socket" -p 55432 -U postgres fantasycard_test
fi
# No failed-source fallback masks missing packages; force the already cached set.
flock -u 8
exec 8>&-
dotnet restore server/FantasyCard.Server.slnx --source "$NUGET_PACKAGES" --ignore-failed-sources -p:MSBuildEnableWorkloadResolver=false -nodeReuse:false
