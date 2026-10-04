#!/bin/bash
# Compiles the 1k most-called contracts with grey and with solc (the reference), keeping the artifacts that the gas
# evaluation reads (evaluation/scripts/gas_offline_replay.py codes). Step `compile` of run_mainnet_gas_evaluation.sh; run it on
# grey-remote, where the corpus and the cores are:
#     evaluation/scripts/compile_variants.sh <work_dir> <grey_src> <results_dir> [jobs]
#   <work_dir>     folder with the inputs file and the corpus it lists (grey-remote: ~/grey_eval, with
#                  inputs_most_called.txt -> corpus/most_called/<address>/<address>_standard_input.json)
#   <grey_src>     the src/ folder of the grey version to evaluate (a copy: its git commit is recorded)
#   <results_dir>  output of compare_variants.py (artifacts/grey and artifacts/solc_solc)
#
# Configuration (environment variables; the defaults are the evaluated configuration, 2026-10-03/04):
#   SOLC_VERSION      official solc of the Yul CFG, the importer and the reference, the same binary on both sides
#                     (default 0.8.35; <work_dir>/bin/solc-<version>, downloaded and sha256-checked if missing)
#   SOLC_BINARY       instead of SOLC_VERSION, a given binary (e.g. bin/solc-without-opt, relative to <work_dir>)
#   FALLBACK_VERSION  solc that generates the Yul CFG when SOLC_VERSION fails there with an internal error (--solc-cfg-
#                     fallback; default 0.8.37; empty: no fallback)
#   GREY_FLAGS        grey's options (default: the evaluated ones below); --debug is always added
#   PROPAGATION       off (default: decide_if_propagated returns False in the evaluated copy, as in the earlier
#                     evaluations) or on
#   DEPTH             maximum stack depth (default 16)
#   INPUTS            the list of compiler inputs in <work_dir> (default inputs_most_called.txt; inputs_semantic.txt for
#                     the semantic tests)
# The given src is copied to <results_dir>/grey_src; the working tree is not modified. The settings used are written to
# <results_dir>/settings.txt.
set -euo pipefail

WORK_DIR=$(realpath "${1:?work dir}")
GREY_SRC=$(realpath "${2:?grey src folder}")
RESULTS_DIR=$(realpath -m "${3:?results dir}")
if [ -n "${4:-}" ]; then
    JOBS=$4
else
    JOBS=$(( $(nproc) - $(cut -d' ' -f1 /proc/loadavg | cut -d. -f1) - 3 ))
    [ "$JOBS" -lt 4 ] && JOBS=4  # the machine is often oversubscribed by other users
fi
# The folder of compare_variants.py: next to this script (evaluation/scripts), or SCRIPTS_DIR (grey-remote:
# ~/grey_eval/scripts)
SCRIPTS_DIR=$(realpath "${SCRIPTS_DIR:-$(dirname "$0")}")
INPUTS=${INPUTS:-inputs_most_called.txt}
SOLC_VERSION=${SOLC_VERSION:-0.8.35}
FALLBACK_VERSION=${FALLBACK_VERSION-0.8.37}
DEPTH=${DEPTH:-16}
PROPAGATION=${PROPAGATION:-off}
DEFAULT_FLAGS="--split-critical-edges --hoist-return-labels --cse --prune-unused-arguments --combine-functions \
--reinline-after-merge --thread-empty-blocks --call-convention orders"
GREY_FLAGS=${GREY_FLAGS:-$DEFAULT_FLAGS}

# The official static binaries of solc (binaries.soliditylang.org), checked against the sha256 of their list
solc_binary() {
    local version=$1 binary=$WORK_DIR/bin/solc-$1
    if [ ! -x "$binary" ]; then
        mkdir -p "$WORK_DIR/bin"
        local entry
        entry=$(curl -sSL -A grey-evaluation https://binaries.soliditylang.org/linux-amd64/list.json |
            python3 -c "import json, sys; build = next(b for b in json.load(sys.stdin)['builds'] if b['version'] == '$version'); print(build['path'], build['sha256'][2:])")
        curl -sSL -A grey-evaluation -o "$binary" "https://binaries.soliditylang.org/linux-amd64/${entry% *}"
        echo "${entry#* }  $binary" | sha256sum --check --quiet
        chmod +x "$binary"
    fi
    echo "$binary"
}

cd "$WORK_DIR"
if [ -n "${SOLC_BINARY:-}" ]; then
    SOLC=$(realpath "$SOLC_BINARY")
else
    SOLC=$(solc_binary "$SOLC_VERSION")
fi
FLAGS="$GREY_FLAGS"
if [ -n "$FALLBACK_VERSION" ]; then
    FALLBACK_SOLC=$(solc_binary "$FALLBACK_VERSION")
    FLAGS="$FLAGS --solc-cfg-fallback $FALLBACK_SOLC"
    "$FALLBACK_SOLC" --version | tail -1
fi

mkdir -p "$RESULTS_DIR"
COMMIT=$(git -C "$GREY_SRC" rev-parse HEAD 2>/dev/null || cat "$GREY_SRC/../COMMIT" 2>/dev/null || echo unknown)
# The evaluated copy, with constant propagation off
EVALUATED_SRC=$RESULTS_DIR/grey_src
rm -rf "$EVALUATED_SRC"
rsync -a --exclude __pycache__ "$GREY_SRC/" "$EVALUATED_SRC/"
PROPAGATION_FILE=$EVALUATED_SRC/cfg_methods/minimizing_constants_insertion.py
if [ "$PROPAGATION" = off ]; then
    sed -i 's/^    return uses \* size >= uses + size + 2.*$/    return False  # propagation off (compile_variants.sh)/' "$PROPAGATION_FILE"
    grep -q "return False  # propagation off" "$PROPAGATION_FILE" || { echo "Could not switch off the propagation"; exit 1; }
fi
GREY_SRC=$EVALUATED_SRC
{
    echo "date $(date -u +%FT%TZ)"
    echo "grey src $COMMIT, copied to $EVALUATED_SRC with constant propagation $PROPAGATION"
    echo "solc $("$SOLC" --version | tail -1)"
    echo "fallback $("$FALLBACK_SOLC" --version | tail -1)"
    echo "flags $FLAGS"
    echo "depth $DEPTH"
    echo "inputs $INPUTS"
    echo "jobs $JOBS"
} > "$RESULTS_DIR/settings.txt"
cat "$RESULTS_DIR/settings.txt"

python3 "$SCRIPTS_DIR/compare_variants.py" "$RESULTS_DIR" --inputs-from "$INPUTS" --force-solc "$SOLC" --depths "$DEPTH" \
    "--flags=--debug" --jobs "$JOBS" --solc-reference --timeout 1800 --keep-artifacts \
    --variant "grey=$GREY_SRC::$FLAGS" > "$RESULTS_DIR.log" 2>&1
find "$RESULTS_DIR/logs" -name '*.txt' -exec gzip -q {} +
tail -5 "$RESULTS_DIR.log"
