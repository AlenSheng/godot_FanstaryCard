#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
source tools/cloud/env.sh
bash tools/cloud/start.sh
evidence="$FANTASYCARD_CLOUD_TOOLS/evidence"
mkdir -p "$evidence"
cleanup() {
  result=$?
  "$FANTASYCARD_CLOUD_TOOLS/postgres/bin/dropdb" -h "$FANTASYCARD_CLOUD_TOOLS/postgres-test/socket" -p 55432 -U postgres --if-exists fantasycard_test || result=1
  bash tools/cloud/stop.sh || result=1
  exit "$result"
}
trap cleanup EXIT
git rev-parse HEAD > "$evidence/source.txt"
dotnet --info > "$evidence/dotnet.txt"
godot --version > "$evidence/godot.txt"
[[ $(cat "$evidence/godot.txt") =~ ^4\.7\.2\. ]]
"$FANTASYCARD_CLOUD_TOOLS/postgres/bin/psql" -h "$FANTASYCARD_CLOUD_TOOLS/postgres-test/socket" -p 55432 -U postgres -d postgres -Atc 'SELECT version()' > "$evidence/postgres.txt"
dotnet test server/tests/FantasyCard.Domain.Tests/FantasyCard.Domain.Tests.csproj -c Release --no-restore --logger 'trx;LogFileName=domain.trx' --results-directory "$evidence"
dotnet test server/tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj -c Release --no-restore --logger 'trx;LogFileName=postgres.trx' --results-directory "$evidence"
python3 tools/cloud/deployment.py tests --directory "$evidence" > "$evidence/test-counts.json"
python3 -m unittest discover -s tools/cloud/tests -v > "$evidence/cloud-tests.log" 2>&1
# The existing helper builds a minimal project with only codec/network fixtures;
# it has no game autoloads and contacts only its disposable loopback HTTP server.
python3 client/tests/run_http_protobuf_client.py --godot "$FANTASYCARD_CLOUD_TOOLS/godot/godot" --work-dir "$evidence/http-fixture" > "$evidence/godot-fixture.log" 2>&1
printf 'Cloud regression complete; PR13 acceptance remains separate.\n'
