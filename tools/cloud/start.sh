#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
source tools/cloud/env.sh
pg_bin=/usr/lib/postgresql/18/bin
pg_root="$FANTASYCARD_CLOUD_TOOLS/postgres-test"
if [[ $(id -u) == 0 ]]; then
  as_pg=(runuser -u postgres --)
  install -d -m 700 -o postgres -g postgres "$pg_root" "$pg_root/socket"
else
  as_pg=()
  mkdir -p "$pg_root/socket"
  chmod 700 "$pg_root" "$pg_root/socket"
fi
if [[ ! -f "$pg_root/data/PG_VERSION" ]]; then
  "${as_pg[@]}" "$pg_bin/initdb" -D "$pg_root/data" -U postgres --auth-local=trust --auth-host=trust --no-locale --encoding=UTF8 >/dev/null
fi
[[ $(cat "$pg_root/data/PG_VERSION") == 18 ]]
if ! "${as_pg[@]}" "$pg_bin/pg_ctl" -D "$pg_root/data" status >/dev/null 2>&1; then
  "${as_pg[@]}" "$pg_bin/pg_ctl" -D "$pg_root/data" -l "$pg_root/postgres.log" -o "-h 127.0.0.1 -p 55432 -k $pg_root/socket -c unix_socket_permissions=0700" -w start >/dev/null
fi
"$pg_bin/pg_isready" -h 127.0.0.1 -p 55432 -U postgres
if ! "$pg_bin/psql" -h 127.0.0.1 -p 55432 -U postgres -d postgres -Atc "SELECT 1 FROM pg_database WHERE datname='fantasycard_test'" | grep -qx 1; then
  "$pg_bin/createdb" -h 127.0.0.1 -p 55432 -U postgres fantasycard_test
fi
# Refresh dependencies on a resumed container. Restore uses the setup-phase cache.
dotnet restore server/FantasyCard.Server.slnx --ignore-failed-sources
