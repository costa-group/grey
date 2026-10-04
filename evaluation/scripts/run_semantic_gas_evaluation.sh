#!/bin/bash
# Semantic tests of solidity (examples/test/semanticTests): bytecode size and gas/correctness of grey vs solc, with
# the same configuration as the mainnet evaluation (compile_variants.sh). Runs in the work folder prepared by
# `run_mainnet_gas_evaluation.sh setup` (step `semantic` of that script, or by hand on the remote):
#     evaluation/scripts/run_semantic_gas_evaluation.sh <work_dir> <grey_src> <results_dir> [jobs]
#   1. compile_variants.sh with INPUTS=inputs_semantic.txt and DEPTH (default 16,8): bytes per input and depth in
#      <results_dir>.log, artifacts in <results_dir>/artifacts;
#   2. gas_semantic_tests.py per depth: the testrunner of solidity's branch testExpectationExtraction on evmone
#      (built by build_testrunner.sh into $TESTRUNNER_ROOT, default <work_dir>/gas/build) executes the traces with
#      solc's and grey's creation codes: <results_dir>_semantic_d<depth>/summary.txt and entries.csv.gz.
# Configuration: the variables of compile_variants.sh (SOLC_VERSION, FALLBACK_VERSION, GREY_FLAGS, PROPAGATION, DEPTH).
set -euo pipefail

WORK_DIR=$(realpath "${1:?work dir}")
GREY_SRC=$(realpath "${2:?grey src folder}")
RESULTS_DIR=$(realpath -m "${3:?results dir}")
JOBS=${4:-}
SCRIPTS_DIR=$(realpath "${SCRIPTS_DIR:-$(dirname "$0")/../../scripts}")
EVALUATION_SCRIPTS=$(realpath "$(dirname "$0")")
TESTRUNNER_ROOT=$(realpath "${TESTRUNNER_ROOT:-$WORK_DIR/gas/build}")
TESTRUNNER=$TESTRUNNER_ROOT/solidity/build/test/tools/testrunner
EVMONE=$TESTRUNNER_ROOT/evmone-94582ffd/build/lib/libevmone.so
[ -x "$TESTRUNNER" ] && [ -f "$EVMONE" ] || { echo "Build the testrunner first: build_testrunner.sh $TESTRUNNER_ROOT"; exit 1; }
export DEPTH=${DEPTH:-16,8}

INPUTS=inputs_semantic.txt "$EVALUATION_SCRIPTS/compile_variants.sh" "$WORK_DIR" "$GREY_SRC" "$RESULTS_DIR" $JOBS
SOLC=$WORK_DIR/bin/solc-${SOLC_VERSION:-0.8.35}
# gas_semantic_tests.py is next to this script, or in SCRIPTS_DIR (on the remote every Python script is in one folder)
SEMANTIC=$EVALUATION_SCRIPTS/gas_semantic_tests.py
[ -f "$SEMANTIC" ] || SEMANTIC=$SCRIPTS_DIR/gas_semantic_tests.py
cd "$WORK_DIR"
for depth in ${DEPTH//,/ }; do
    PYTHONPATH="$SCRIPTS_DIR:$EVALUATION_SCRIPTS${PYTHONPATH:+:$PYTHONPATH}" python3 "$SEMANTIC" "$RESULTS_DIR" \
        --inputs-from inputs_semantic.txt --solc "$SOLC" --depth "$depth" ${JOBS:+--jobs $JOBS} \
        --variant solc=solc_solc --variant grey=grey --testrunner "$TESTRUNNER" --evmone "$EVMONE" \
        --out-dir "${RESULTS_DIR}_semantic_d$depth" > "${RESULTS_DIR}_semantic_d$depth.log" 2>&1
    sed -n 1,20p "${RESULTS_DIR}_semantic_d$depth/summary.txt"
done
