#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
[[ $(uname -s) == Linux && $(uname -m) == x86_64 && $(id -u) != 0 ]] || { echo 'Unprivileged Linux x64 required' >&2; exit 1; }
# The cloud image must already provide compiler, make, Perl, dpkg-deb, Python venv,
# and runtime libraries (ICU, SSL, X11/GL). No host apt/sudo/runner registration.
for prerequisite in cc make perl dpkg-deb python3; do command -v "$prerequisite" >/dev/null; done
source tools/cloud/env.sh
mkdir -p "$XDG_CACHE_HOME" "$XDG_CONFIG_HOME" "$XDG_DATA_HOME"
python3 tools/cloud/install_tools.py
source tools/cloud/env.sh
python3 -m venv "$FANTASYCARD_CLOUD_TOOLS/venv"
"$FANTASYCARD_CLOUD_TOOLS/venv/bin/python" -m pip install --disable-pip-version-check psutil==7.0.0
# This phase needs approved NuGet/package network access; Start uses the cache.
dotnet restore server/FantasyCard.Server.slnx
bash tools/cloud/start.sh
printf 'Setup complete. Source tools/cloud/env.sh in each shell.\n'
