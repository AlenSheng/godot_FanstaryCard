#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
source tools/cloud/env.sh
pg_root="$FANTASYCARD_CLOUD_TOOLS/postgres-test"
[[ -f "$pg_root/data/PG_VERSION" ]] || exit 0
exec 8>"$pg_root/start.lock"
flock -x 8
if "$FANTASYCARD_CLOUD_TOOLS/postgres/bin/pg_ctl" -D "$pg_root/data" status >/dev/null 2>&1; then
  "$FANTASYCARD_CLOUD_TOOLS/postgres/bin/pg_ctl" -D "$pg_root/data" -m fast -w stop >/dev/null
fi
