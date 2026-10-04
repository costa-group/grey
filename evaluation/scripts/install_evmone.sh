#!/bin/bash
# Installs the evmone CLI of a pinned release (its `evmone t8n` subcommand is the state transition tool used by
# evaluation/scripts/gas_offline_replay.py; the standalone evmone-t8n was folded into it). The release binary needs glibc >= 2.38:
# use grey-remote (2.39), not the local machine (2.31).
# Usage: install_evmone.sh <install_root>      ->  <install_root>/evmone-<version>/evmone (wrapper)
# The binary has no RPATH, so the wrapper points LD_LIBRARY_PATH to the release's lib/.
# Independent of build_testrunner.sh: testrunner needs an evmone library with EVMC ABI 12, this one has its own.
set -euo pipefail

INSTALL_ROOT=$(realpath -m "${1:?install root}")
VERSION=0.24.0
SHA256=aa98906ec5bc2e0a8d3ae86c1e18a1c9bf56cc0252f01ef50472a6a5621dc734
FOLDER="$INSTALL_ROOT/evmone-$VERSION"
if [ ! -x "$FOLDER/bin/evmone" ]; then
    mkdir -p "$FOLDER"
    archive="$FOLDER/evmone-$VERSION-linux-x86_64.tar.gz"
    curl -sSL -o "$archive" "https://github.com/ipsilon/evmone/releases/download/v$VERSION/evmone-$VERSION-linux-x86_64.tar.gz"
    echo "$SHA256  $archive" | sha256sum --check --quiet
    tar xzf "$archive" -C "$FOLDER"
fi
cat > "$FOLDER/evmone" <<WRAPPER
#!/bin/bash
LD_LIBRARY_PATH="$FOLDER/lib\${LD_LIBRARY_PATH:+:\$LD_LIBRARY_PATH}" exec "$FOLDER/bin/evmone" "\$@"
WRAPPER
chmod +x "$FOLDER/evmone"
"$FOLDER/evmone" t8n --help > /dev/null
echo "evmone $VERSION: $FOLDER/evmone (wrapper of bin/evmone; t8n subcommand)"
