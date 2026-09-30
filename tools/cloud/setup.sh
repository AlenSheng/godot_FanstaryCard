#!/usr/bin/env bash
set -euo pipefail
[[ $(uname -s) == Linux && $(uname -m) == x86_64 ]] || { echo 'Linux x64 only' >&2; exit 1; }
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
source tools/cloud/env.sh
if [[ $(id -u) == 0 ]]; then elevate=(); else elevate=(sudo -n); fi
"${elevate[@]}" apt-get update -qq
"${elevate[@]}" apt-get install -y --no-install-recommends ca-certificates curl gnupg python3-venv libicu-dev libssl3 libx11-6 libxcursor1 libxinerama1 libxi6 libxrandr2 libgl1 libasound2t64
# Official PostgreSQL repository. This operates only inside the disposable cloud container.
source /etc/os-release
[[ $ID == ubuntu && $VERSION_CODENAME =~ ^[a-z]+$ ]] || { echo 'Expected Ubuntu cloud image' >&2; exit 1; }
curl --fail --location --retry 3 https://www.postgresql.org/media/keys/ACCC4CF8.asc -o /tmp/fantasycard-pg-key.asc
gpg --show-keys --with-colons /tmp/fantasycard-pg-key.asc | grep -q '^fpr:::::::::B97B0AFCAA1A47F044F244A07FCC7D46ACCC4CF8:'
"${elevate[@]}" install -m 644 /tmp/fantasycard-pg-key.asc /usr/share/keyrings/fantasycard-pgdg.asc
printf 'deb [signed-by=/usr/share/keyrings/fantasycard-pgdg.asc] https://apt.postgresql.org/pub/repos/apt %s-pgdg main\n' "$VERSION_CODENAME" | "${elevate[@]}" tee /etc/apt/sources.list.d/fantasycard-pgdg.list >/dev/null
"${elevate[@]}" apt-get update -qq
"${elevate[@]}" apt-get install -y --no-install-recommends postgresql-18 postgresql-client-18
"${elevate[@]}" mkdir -p "$FANTASYCARD_CLOUD_TOOLS"
"${elevate[@]}" chown "$(id -u):$(id -g)" "$FANTASYCARD_CLOUD_TOOLS"
python3 tools/cloud/install_tools.py
python3 -m venv "$FANTASYCARD_CLOUD_TOOLS/venv"
python -m pip install psutil==7.0.0
# Cache NuGet for an agent phase with outbound networking disabled.
dotnet restore server/FantasyCard.Server.slnx
bash tools/cloud/start.sh
printf 'Setup complete. In each agent shell: source tools/cloud/env.sh\n'
