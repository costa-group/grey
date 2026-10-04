#!/bin/bash
# Gas evaluation of grey vs solc on real mainnet transactions of the 1k most-called contracts, from scratch.
# Every step can be run on its own and repeated (each one skips the work already done). Run from the repo root:
#     evaluation/scripts/run_mainnet_gas_evaluation.sh <step> [<step> ...]      e.g.  ... dry-run   ... import sample
#     evaluation/scripts/run_mainnet_gas_evaluation.sh all                       (every step, asking before paying)
#
# Steps (see evaluation/README.md and PROGRESS.md 2026-10-01/02 for the reasons behind each decision):
#   query     regenerate evaluation/scripts/bigquery/sample_txs.sql from the ABIs (must not change the committed file)
#   dry-run   bytes the query would read (free)
#   run       run the query once into $BQ_TABLE (PAID: ~2.04 TiB, about $13 on demand, on 2026-10-02)
#   import    read $BQ_TABLE into $DATA_DIR/bigquery/sample_txs.json.gz (committed: the later steps start from it)
#   sample    sample size and contracts without transactions
#   load      split the sample per contract ($DATA_DIR/txs/<address>.json.gz, 20 per (contract, function));
#             contracts without ABI functions: raw selectors with < 20 transactions are merged into 'other'
#   deploy    creator, nonce, constructor arguments and immutables per contract (Etherscan + Sourcify)
#   prestate  per transaction: signed transaction, receipt, block header and prestate (RPC, resumable;
#             JOBS=16, REQUESTS_PER_SECOND=40 by default)
#   resolve   contracts whose source came from Etherscan (not on Sourcify): recompile the original input with its
#             compiler, find the on-chain code it matches (for minimal clones and ERC-1967 proxies, Etherscan gives the
#             implementation's source: the variants' code then goes at the implementation) and read the immutables
#             from it; updates $DATA_DIR/deploy and writes $DATA_DIR/etherscan_resolution.csv (local, after prestate)
#   immutables  key the on-chain values of the immutables by the AST ids of the corpus inputs (the variants'
#             numbering): when Sourcify's ids differ, recompile the original input, read the values from the on-chain
#             code and match them by declaration (Contract.variable); writes $DATA_DIR/immutables_resolution.csv
#             (local, after resolve)
# The following steps run on $REMOTE (grey-remote: the corpus, the cores, and glibc >= 2.38 for evmone); they copy
# what they need with rsync and run there over ssh:
#   compile   compile the 1k with the current grey (src/) and with solc, keeping the artifacts
#             (evaluation/scripts/compile_variants.sh: flags, solc 0.8.35 + 0.8.37 fallback, propagation off)
#   codes     runtime code per contract for solc and grey, with the on-chain immutables and linked libraries (no
#             constructor run), in $REMOTE_DIR/results/$RESULTS_NAME/codes
#   replay    offline replay with `evmone t8n` (0.24.0): receipt check under the block's fork, then the original,
#             solc and grey under Prague; status, logs and state must match the original
#   report    gas per variant, plain and weighted by function frequency; copied back to $DATA_DIR/results
#   setup     (once) prepare $REMOTE_DIR: the corpora (examples/most_called_0_8/test_most_called,
#             examples/test/semanticTests) and their input lists, the official solc binaries, and pyshim/ (only
#             needed where pygraphviz is missing)
#   blockhashes  (local, after a first replay + report) the hashes of the blocks older than the parent that the
#             transactions with an invalid receipt check read with BLOCKHASH (VRF proofs, randomness), fetched from the
#             RPC into their entries; then run replay and report again
#   semantic  bytes and gas on solidity's semantic tests with the same configuration (run_semantic_gas_evaluation.sh;
#             builds the testrunner with build_testrunner.sh the first time; depths SEMANTIC_DEPTHS, default 16,8)
#   diagnosis classify every mismatch with the original (gas_mismatch_diagnosis.py): gas- or code-dependent, or
#             unexplained
#
# Fixed decisions (the user's, 2026-10-02):
#   - period: the ranking's (examples/most_called_0_8/contract_list_all.csv): blocks 11,565,019 (2021-01-01) to
#     24,580,372 (2026-03-03 23:59:59); the ranking was computed between 2026-01-30 and 2026-03-04;
#   - direct, successful transactions; 20 per (contract, ABI function), plus 'other' (calls outside the ABI);
#     contracts whose ABI has no functions by raw selector; random order FARM_FINGERPRINT(hash);
#   - every transaction replayed under Prague for all variants (the same rules for all); its own fork only checks the
#     original replay against the receipt.
#
# Configuration (environment variables):
#   BQ_PROJECT    Google Cloud project billed for the query, required (transactions-evm on 2026-10-02)
#   BQ_TABLE      destination table, default $BQ_PROJECT:grey_gas.sample_txs_ranking_2021_2026 (dataset in US)
#   DATA_DIR      default evaluation/data/mainnet
#   ETHERSCAN_API_KEY   for the deploy step (Etherscan V2)
#   RPC_FILE      file with the RPC URL (archive + debug_traceTransaction; https://eth.drpc.org works, free)
#   CONFIRM=1     do not ask before the paid step
#   REMOTE        ssh host of the remote steps (grey-remote; localhost also works); REMOTE_DIR its work folder
#                 (grey_eval, relative to the remote home), prepared by the step `setup`
#   RESULTS_NAME  name of the compilation under $REMOTE_DIR/results (gas_<grey commit>_most_called by default)
#   SOLC_VERSION, FALLBACK_VERSION, GREY_FLAGS, PROPAGATION, DEPTH: the configuration of the compared code (see
#                 compile_variants.sh; the defaults are the evaluated configuration). They are passed to the remote
#                 compilation, and SOLC_VERSION is also used by the codes and immutables steps
set -euo pipefail

REPO_ROOT=$(git rev-parse --show-toplevel)
cd "$REPO_ROOT"
# The evaluation scripts, and the comparison scripts they share with the other experiments
SCRIPTS=evaluation/scripts
REPOSITORY_SCRIPTS=scripts
QUERY=evaluation/scripts/bigquery/sample_txs.sql
ADDRESSES=evaluation/data/inputs_most_called.txt
DATA_DIR=${DATA_DIR:-evaluation/data/mainnet}
EXPORT=$DATA_DIR/bigquery/sample_txs.json.gz
BQ_TABLE=${BQ_TABLE:-${BQ_PROJECT:-}:grey_gas.sample_txs_ranking_2021_2026}
PER_BUCKET=20
# Before running: python3 with pandas and pycryptodome, the Google Cloud CLI (bq), and for the later steps
# the tools of evaluation/scripts/build_testrunner.sh / install_foundry.sh
replay() { PYTHONDONTWRITEBYTECODE=1 python3 "$SCRIPTS/gas_mainnet_replay.py" "$@"; }
REMOTE=${REMOTE:-grey-remote}
REMOTE_DIR=${REMOTE_DIR:-grey_eval}
COMMIT=$(git rev-parse --short HEAD)
RESULTS_NAME=${RESULTS_NAME:-gas_${COMMIT}_most_called}
REMOTE_DATA=$REMOTE_DIR/gas/$(basename "$DATA_DIR")
# Runs a command on the remote work folder (PYTHONPATH with pyshim, as the other runs there)
# On the remote, every Python script is in one folder ($REMOTE_DIR/scripts) and the Etherscan data in $REMOTE_DIR/data
on_remote() { ssh -o ServerAliveInterval=60 "$REMOTE" "cd $REMOTE_DIR && export PYTHONPATH=\$PWD/pyshim SCRIPTS_DIR=\$PWD/scripts ETHERSCAN_FOLDER=\$PWD/data/etherscan && $*"; }
sync_scripts() {
    on_remote "mkdir -p scripts gas/scripts data"
    rsync -a "$SCRIPTS"/gas_common.py "$SCRIPTS"/gas_mainnet_replay.py "$SCRIPTS"/gas_offline_replay.py \
        "$SCRIPTS"/gas_mismatch_diagnosis.py "$SCRIPTS"/gas_semantic_tests.py "$SCRIPTS"/compare_variants.py \
        "$REPOSITORY_SCRIPTS"/compare_repair_slots.py \
        "$REPOSITORY_SCRIPTS"/compare_with_solc.py "$REPOSITORY_SCRIPTS"/check_equivalence_hevm.py \
        "$REMOTE:$REMOTE_DIR/scripts/"
    rsync -a "$SCRIPTS"/compile_variants.sh "$SCRIPTS"/install_evmone.sh "$REMOTE:$REMOTE_DIR/gas/scripts/"
    # gas_offline_replay.py reads the contract names and original inputs from the Etherscan data
    rsync -a evaluation/data/etherscan "$REMOTE:$REMOTE_DIR/data/"
}
sync_data() { rsync -a "$DATA_DIR"/txs "$DATA_DIR"/codes "$DATA_DIR"/deploy "$REMOTE:$REMOTE_DATA/"; }

require_project() {
    if [ -z "${BQ_PROJECT:-}" ]; then
        echo "Set BQ_PROJECT, the Google Cloud project billed, on the same line: BQ_PROJECT=<project> $0 ..."
        exit 1
    fi
    echo "project $BQ_PROJECT, table $BQ_TABLE"
}

step_query() {
    replay make-bigquery-query "$ADDRESSES" --output "$QUERY"
    if ! git diff --quiet -- "$QUERY"; then
        echo "WARNING: the regenerated query differs from the committed one (git diff $QUERY)"
    fi
}

step_dry_run() {
    require_project
    bq --project_id="${BQ_PROJECT}" query --dry_run --use_legacy_sql=false < "$QUERY"
}

step_run() {
    require_project
    if bq --project_id="${BQ_PROJECT}" show "$BQ_TABLE" > /dev/null 2>&1; then
        echo "$BQ_TABLE already exists: not running the query again (delete it to rerun: bq rm -t $BQ_TABLE)"
        return
    fi
    if [ "${CONFIRM:-0}" != 1 ]; then
        read -r -p "This query is billed (see dry-run). Run it into $BQ_TABLE? [y/N] " answer
        [ "$answer" = y ] || { echo "Not run"; exit 1; }
    fi
    bq --project_id="${BQ_PROJECT}" mk --dataset --location=US "${BQ_TABLE%.*}" 2> /dev/null || true
    bq --project_id="${BQ_PROJECT}" query --use_legacy_sql=false --destination_table="$BQ_TABLE" --replace < "$QUERY"
}

step_import() {
    if [ -f "$EXPORT" ]; then echo "$EXPORT exists"; return; fi
    require_project
    local rows tmp
    rows=$(bq --project_id="${BQ_PROJECT}" --format=json show "$BQ_TABLE" | python3 -c "import json,sys;print(json.load(sys.stdin)['numRows'])")
    tmp=$(mktemp)
    bq --project_id="${BQ_PROJECT}" --format=json head -n $((rows + 1)) "$BQ_TABLE" > "$tmp"
    replay import-bigquery-json "$tmp" "$EXPORT" --expected-rows "$rows"
    rm -f "$tmp"
    echo "Commit $EXPORT: the following steps start from it (the BigQuery table can then be deleted)"
}

step_sample() { replay sample-size "$ADDRESSES" "$EXPORT" --per-bucket "$PER_BUCKET"; }

step_load() { replay load-bigquery "$EXPORT" "$DATA_DIR" --per-bucket "$PER_BUCKET"; }

step_deploy() {
    if [ -z "${ETHERSCAN_API_KEY:-}" ]; then echo "Set ETHERSCAN_API_KEY"; exit 1; fi
    replay fetch-deploy "$ADDRESSES" "$DATA_DIR" ${RPC_FILE:+--rpc-file "$RPC_FILE"}
}

step_prestate() {
    # Resumable: run it again to complete the transactions that failed. ~4 RPC requests per transaction; the codes
    # are stored once in $DATA_DIR/codes (~255 MB in total for the 87,763 transactions; run locally on 2026-10-03)
    replay fetch-prestate "$DATA_DIR" ${RPC_FILE:+--rpc-file "$RPC_FILE"} --jobs "${JOBS:-16}" \
        --requests-per-second "${REQUESTS_PER_SECOND:-40}"
}

step_resolve() {
    PYTHONDONTWRITEBYTECODE=1 python3 "$SCRIPTS/gas_offline_replay.py" resolve-etherscan "$DATA_DIR"
}

step_immutables() {
    PYTHONDONTWRITEBYTECODE=1 python3 "$SCRIPTS/gas_offline_replay.py" resolve-immutables "$DATA_DIR" \
        --solc "${LOCAL_SOLC:-$HOME/.solc-select/artifacts/solc-${SOLC_VERSION:-0.8.35}/solc-${SOLC_VERSION:-0.8.35}}"
}

step_setup() {
    ssh "$REMOTE" "mkdir -p $REMOTE_DIR/corpus $REMOTE_DIR/bin $REMOTE_DIR/pyshim $REMOTE_DIR/results"
    rsync -a examples/most_called_0_8/test_most_called/ "$REMOTE:$REMOTE_DIR/corpus/most_called/"
    rsync -a examples/test/semanticTests/ "$REMOTE:$REMOTE_DIR/corpus/semanticTests/"
    rsync -a "$SCRIPTS"/pyshim/sitecustomize.py "$REMOTE:$REMOTE_DIR/pyshim/"
    on_remote "find corpus/most_called -name '*_standard_input.json' | sort > inputs_most_called.txt && \
        find corpus/semanticTests -name '*_standard_input.json' | sort > inputs_semantic.txt && \
        wc -l inputs_most_called.txt inputs_semantic.txt"
    sync_scripts
}

# The configuration of the compared code, passed to the remote compilation
configuration() {
    printf 'SOLC_VERSION=%q FALLBACK_VERSION=%q GREY_FLAGS=%q PROPAGATION=%q DEPTH=%q' "${SOLC_VERSION:-0.8.35}" \
        "${FALLBACK_VERSION-0.8.37}" "${GREY_FLAGS:-}" "${PROPAGATION:-off}" "${DEPTH:-16}"
}

step_compile() {
    sync_scripts
    on_remote "mkdir -p near_src/$COMMIT"
    rsync -a --delete --exclude __pycache__ src/ "$REMOTE:$REMOTE_DIR/near_src/$COMMIT/src/"
    git rev-parse HEAD | ssh "$REMOTE" "cat > $REMOTE_DIR/near_src/$COMMIT/COMMIT"
    on_remote "$(configuration) gas/scripts/compile_variants.sh \$PWD \$PWD/near_src/$COMMIT/src \$PWD/results/$RESULTS_NAME ${JOBS:-}"
}

step_codes() {
    sync_scripts
    sync_data
    on_remote "python3 scripts/gas_offline_replay.py codes gas/$(basename "$DATA_DIR") results/$RESULTS_NAME \
        --inputs-from inputs_most_called.txt --solc bin/solc-${SOLC_VERSION:-0.8.35} --variant solc=solc_solc --variant grey=grey \
        --variants-dir results/$RESULTS_NAME/codes ${JOBS:+--jobs $JOBS}"
}

step_replay() {
    sync_scripts
    sync_data
    on_remote "gas/scripts/install_evmone.sh gas/build && python3 scripts/gas_offline_replay.py replay \
        gas/$(basename "$DATA_DIR") --variants solc,grey --t8n gas/build/evmone-0.24.0/evmone --engine evmone \
        --out-dir results/${RESULTS_NAME}_replay --variants-dir results/$RESULTS_NAME/codes ${JOBS:+--jobs $JOBS}"
}

step_report() {
    on_remote "python3 scripts/gas_offline_replay.py report results/${RESULTS_NAME}_replay gas/$(basename "$DATA_DIR")"
    mkdir -p "$DATA_DIR/results/${RESULTS_NAME}"
    rsync -a "$REMOTE:$REMOTE_DIR/results/${RESULTS_NAME}_replay/" "$DATA_DIR/results/${RESULTS_NAME}/"
    rsync -a "$REMOTE:$REMOTE_DIR/results/$RESULTS_NAME/settings.txt" "$DATA_DIR/results/${RESULTS_NAME}/compile_settings.txt"
    echo "Results in $DATA_DIR/results/${RESULTS_NAME}"
}

step_semantic() {
    sync_scripts
    rsync -a "$SCRIPTS"/run_semantic_gas_evaluation.sh "$SCRIPTS"/build_testrunner.sh "$SCRIPTS"/testrunner_logs.patch \
        "$REMOTE:$REMOTE_DIR/gas/scripts/"
    on_remote "mkdir -p near_src/$COMMIT"
    rsync -a --delete --exclude __pycache__ src/ "$REMOTE:$REMOTE_DIR/near_src/$COMMIT/src/"
    git rev-parse HEAD | ssh "$REMOTE" "cat > $REMOTE_DIR/near_src/$COMMIT/COMMIT"
    on_remote "[ -x gas/build/solidity/build/test/tools/testrunner ] || gas/scripts/build_testrunner.sh gas/build; \
        $(configuration) DEPTH=${SEMANTIC_DEPTHS:-16,8} gas/scripts/run_semantic_gas_evaluation.sh \$PWD \
        \$PWD/near_src/$COMMIT/src \$PWD/results/semantic_$COMMIT ${JOBS:-}"
    rsync -a "$REMOTE:$REMOTE_DIR/results/semantic_${COMMIT}_semantic_d*" "$DATA_DIR/results/" 2>/dev/null || true
}

step_blockhashes() {
    PYTHONDONTWRITEBYTECODE=1 python3 "$SCRIPTS/gas_offline_replay.py" fetch-blockhashes "$DATA_DIR" \
        --replay-dir "$DATA_DIR/results/${RESULTS_NAME}" --t8n "${LOCAL_T8N:-evm}" ${RPC_FILE:+--rpc-file "$RPC_FILE"}
}

step_diagnosis() {
    sync_scripts
    on_remote "python3 scripts/gas_mismatch_diagnosis.py gas/$(basename "$DATA_DIR") results/${RESULTS_NAME}_replay \
        --variants-dir results/$RESULTS_NAME/codes --t8n gas/build/evmone-0.24.0/evmone \
        --out-dir results/${RESULTS_NAME}_replay/diagnosis ${JOBS:+--jobs $JOBS}"
    rsync -a "$REMOTE:$REMOTE_DIR/results/${RESULTS_NAME}_replay/diagnosis/" "$DATA_DIR/results/${RESULTS_NAME}/diagnosis/"
}

run_step() {
    case "$1" in
        setup) step_setup ;;
        query) step_query ;;
        dry-run) step_dry_run ;;
        run) step_run ;;
        import) step_import ;;
        sample) step_sample ;;
        load) step_load ;;
        deploy) step_deploy ;;
        prestate) step_prestate ;;
        resolve) step_resolve ;;
        immutables) step_immutables ;;
        compile) step_compile ;;
        codes) step_codes ;;
        replay) step_replay ;;
        report) step_report ;;
        blockhashes) step_blockhashes ;;
        semantic) step_semantic ;;
        diagnosis) step_diagnosis ;;
        *) echo "Unknown step: $1"; exit 1 ;;
    esac
}

if [ $# -lt 1 ]; then
    # The header comment (up to the first line that is not a comment), then the usage
    awk 'NR > 1 && !/^#/ {exit} NR > 1 {sub(/^# ?/, ""); print}' "$0"
    echo
    echo "Usage: $0 <step> [<step> ...] | all      e.g. BQ_PROJECT=<project> $0 dry-run"
    exit 1
fi
if [ "$1" = all ]; then
    set -- query dry-run run import sample load deploy prestate resolve immutables compile codes replay report \
        blockhashes replay report diagnosis
fi
for step in "$@"; do
    echo "== $step"
    run_step "$step"
done
