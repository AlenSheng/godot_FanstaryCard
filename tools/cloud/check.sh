#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
source tools/cloud/env.sh
bash tools/cloud/start.sh
mkdir -p test-results/cloud
git rev-parse HEAD > test-results/cloud/source.txt
dotnet --info > test-results/cloud/dotnet.txt
godot --version > test-results/cloud/godot.txt
grep -q '^4\.7\.2\.' test-results/cloud/godot.txt
/usr/lib/postgresql/18/bin/psql -h 127.0.0.1 -p 55432 -U postgres -d postgres -Atc 'SELECT version()' > test-results/cloud/postgres.txt
dotnet test server/tests/FantasyCard.Domain.Tests/FantasyCard.Domain.Tests.csproj -c Release --no-restore --logger 'trx;LogFileName=domain.trx' --results-directory "$PWD/test-results/cloud"
dotnet test server/tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj -c Release --no-restore --logger 'trx;LogFileName=server.trx' --results-directory "$PWD/test-results/cloud"
python -m unittest discover -s tools/cloud/tests -v
if [[ -d tools/tests ]]; then python -m unittest discover -s tools/tests -v; fi
# Run the existing client fixtures, only after an isolated import. No cloud server address is used.
export XDG_DATA_HOME="$FANTASYCARD_CLOUD_TOOLS/client/data" XDG_CONFIG_HOME="$FANTASYCARD_CLOUD_TOOLS/client/config" XDG_CACHE_HOME="$FANTASYCARD_CLOUD_TOOLS/client/cache"
if [[ $(id -u) == 0 ]]; then isolate=(unshare -n); else isolate=(sudo -n -E unshare -n); fi
"${isolate[@]}" timeout 600 godot --headless --path client --editor --import --quit > test-results/cloud/import.log 2>&1
! grep -E 'SCRIPT ERROR|Parse Error|Failed to load script' test-results/cloud/import.log
python client/tests/run_http_protobuf_client.py --godot "$FANTASYCARD_CLOUD_TOOLS/godot/godot" --work-dir test-results/cloud/http-fixture
printf 'Cloud environment regression complete; this is not the PR13 acceptance register.\n'
