#!/bin/bash
# Full evaluation of grey vs solc for one configuration of both, printing the final results. Run from the repository
# root, on the grey version to evaluate (the working tree's src/, uncommitted changes included):
#
#     GREY_FLAGS="<grey options>" SOLC=<version or binary> evaluation/scripts/evaluate.sh
#
# e.g. SOLC=0.8.35 (the default, official binary), or SOLC=examples/solc-without-opt (solc without the legacy optimizer,
# used on both sides). The rest of the configuration: PROPAGATION (off), DEPTH (16), FALLBACK_VERSION (0.8.37; empty for
# none), SEMANTIC_DEPTHS (16,8); SKIP_SEMANTIC=1 skips the semantic tests. Work machine: REMOTE (grey-remote) and
# REMOTE_DIR (grey_eval); JOBS (default: the free cores).
#
# Steps (those of run_mainnet_gas_evaluation.sh):
#   1. setup: corpora, input lists and scripts on the work machine (fast once done);
#   2. the RPC data, if missing: the sample of each contract (load) and the prestates (prestate, hours on a free RPC);
#   3. immutables: the on-chain immutable values keyed by the AST ids of the corpus inputs for this solc;
#   4. compile, codes, replay, report: the mainnet transactions;
#   5. blockhashes: older block hashes read by transactions whose receipt check failed (then replay and report again,
#      only if any was fetched);
#   6. diagnosis: every mismatch with the original classified, and every sampled transaction accounted for;
#   7. semantic: size, correctness and gas on the semantic tests;
#   8. the final results (summarize_evaluation.py), also written to <results>/final_results.txt.
# The results are in evaluation/data/mainnet/results/<RESULTS_NAME> (by default gas_<commit>_<solc>_<configuration hash>).
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"
DRIVER=evaluation/scripts/run_mainnet_gas_evaluation.sh
DATA_DIR=${DATA_DIR:-evaluation/data/mainnet}
export DATA_DIR
RESULTS=$("$DRIVER" results-dir | tail -1)
echo "== Evaluation into $RESULTS"

"$DRIVER" setup
if [ ! -d "$DATA_DIR/txs" ] || [ -z "$(ls -A "$DATA_DIR/txs" 2> /dev/null)" ]; then
    echo "== No RPC data in $DATA_DIR/txs: loading the sample and fetching the prestates (resumable)"
    "$DRIVER" load prestate
fi
"$DRIVER" immutables compile codes replay report
fetched=$("$DRIVER" blockhashes | tee /dev/stderr | grep -c "block hashes" || true)
if [ "$fetched" -gt 0 ]; then
    echo "== Block hashes fetched for $fetched contracts: replaying again"
    "$DRIVER" replay report
fi
"$DRIVER" diagnosis
if [ "${SKIP_SEMANTIC:-0}" != 1 ]; then
    "$DRIVER" semantic
fi
echo
python3 evaluation/scripts/summarize_evaluation.py "$RESULTS"
