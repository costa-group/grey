#!/bin/bash
# Installs foundry (anvil, cast) into ~/.foundry at a pinned version, for gas_mainnet_replay.py.
# Usage: install_foundry.sh [version]   (default: the version used in the 2026-10 evaluation; "stable" for the newest)
set -euo pipefail
VERSION=${1:-v1.8.3}
if [ ! -x "$HOME/.foundry/bin/foundryup" ]; then
    curl -sSL https://foundry.paradigm.xyz | bash > /dev/null
fi
"$HOME/.foundry/bin/foundryup" --install "$VERSION"
"$HOME/.foundry/bin/anvil" --version
