# Evaluation of grey vs solc: bytecode size and gas

This folder contains everything needed to compare the code that grey generates with solc's, for a given configuration of
both:

- **Mainnet transactions:** 87,763 real transactions of the 1,000 most-called contracts, replayed offline on their
  original state with each variant's code. For each transaction, the replay checks that the variant behaves like the
  deployed contract and measures its gas.
- **Semantic tests:** solidity's own test suite, executed with solidity's `testrunner` on evmone.
- **Bytecode size**, for both corpora.

This README explains how to install the tools, how to obtain the data, how to run an evaluation for a given
configuration of grey and solc, and how the transactions are compared.

## 1. Layout

```
evaluation/
  scripts/
    evaluate.sh                     the whole evaluation of one configuration, printing the final results
    run_mainnet_gas_evaluation.sh   driver of the pipeline, step by step
    summarize_evaluation.py         the final results of a run, from its results folder
    compile_variants.sh             compiles a corpus with grey and with solc, for a configuration of both
    run_semantic_gas_evaluation.sh  semantic tests: size, correctness and gas
    gas_mainnet_replay.py           data collection: Etherscan, BigQuery sample, Sourcify/Etherscan deployment data,
                                    RPC prestates (fetch-*, load-bigquery, ...)
    gas_offline_replay.py           resolve-etherscan, resolve-immutables, codes, replay, fetch-blockhashes, report
    gas_mismatch_diagnosis.py       classifies every mismatch with the original, and accounts for every transaction
    gas_semantic_tests.py           runs solidity's testrunner with each variant's creation code
    gas_common.py                   shared helpers (compiling, linking, immutables)
    compare_variants.py             compiles a corpus with grey variants and the solc reference, keeping the artifacts
                                    (bytes, memory slots, bytecode statistics)
    compare_traces.py               debugging: where two codes spend gas differently on a call (geth traces)
    bigquery/sample_txs.sql         the BigQuery query of the transaction sample
    build_testrunner.sh             builds solidity's testrunner and evmone for the semantic tests
    testrunner_logs.patch           applied by build_testrunner.sh: makes testrunner also record a digest of the
                                    logs and of the storage after each call (it only checks status and return data)
    install_evmone.sh               installs the evmone release used for the mainnet replay
    install_foundry.sh              installs anvil (only for the earlier, RPC-based replay of gas_mainnet_replay.py)
    pyshim/                         disables grey's .dot debug dumps where pygraphviz is not installed
  data/
    inputs_most_called.txt   the corpus inputs of the 1,000 contracts
    etherscan/<address>.json Etherscan's getsourcecode: original input, compiler version and settings, ABI, libraries
    mainnet/                 data of the mainnet evaluation:
      bigquery/sample_txs.json.gz   the BigQuery sample (committed: the paid query need not be repeated)
      deploy/<address>.json.gz      deployment data: creator, constructor arguments, immutables (Sourcify,
                                    Etherscan), proxy resolution
      etherscan_resolution.csv, immutables_resolution.csv
      txs/, codes/             RPC data: per transaction, its prestate, receipt and header (not committed)
      results/<name>/          outputs of each run (not committed)
  results/                 results of earlier runs
```

The general comparison scripts that other experiments also use stay in the repository's `scripts/`:
`compare_with_solc.py`, `compare_repair_slots.py` and `check_equivalence_hevm.py`. The evaluation scripts import them
from there.

The corpora are in the repository:
- `examples/most_called_0_8/test_most_called/<address>/<address>_standard_input.json`: one compiler input per
  contract. Their sources are rewritten for the experiments (pragma `^0.8.34`, `viaIR`, `runs` 200, no metadata);
  the originals are in `data/etherscan`.
- `examples/most_called_0_8/contract_list_all.csv`: the ranking that selected them.
- `examples/test/semanticTests/<name>/`: the semantic tests, each with its input and its trace.

## 2. Requirements

**Local machine** (data collection, `resolve`, `immutables`, `blockhashes`, and the driver):
- Python ≥ 3.10 with `pandas` and `pycryptodome`, plus grey's own requirements (`pyproject.toml`:
  `networkx`, `pygraphviz`...). `pip install pandas pycryptodome networkx`;
- `git`, `rsync`, `ssh`, `curl`;
- solc binaries:
  - the evaluated version (0.8.35) at `~/.solc-select/artifacts/solc-0.8.35/solc-0.8.35`
    (`pip install solc-select && solc-select install 0.8.35`), or another path in `LOCAL_SOLC`;
  - the original compilers of the contracts are downloaded when needed into `~/.cache/grey/solc` (official binaries,
    sha256-checked);
- geth's `evm` (go-ethereum 1.16.5 used) for `fetch-blockhashes`;
- only to regenerate the data:
  - an Etherscan API key (`ETHERSCAN_API_KEY`, free tier);
  - an Ethereum RPC with archive state and `debug_traceTransaction` (`https://eth.drpc.org` works, free, rate-limited;
    `RPC_FILE`: a file with another URL);
  - for the BigQuery sample, the Google Cloud CLI (`bq`) and a billed project (`BQ_PROJECT`; the query reads
    ~2.04 TiB, about $13 on demand).

**Work machine** (`REMOTE`, reached by ssh; `localhost` also works): compiles the corpora and replays the
transactions. Many cores help: the evaluation took ~25 min with 60 jobs on 128 cores.
- Python 3 with `pandas` and grey's requirements. Without `pygraphviz`, `pyshim/` disables the `.dot` dumps of
  `--debug`, which are its only use;
- glibc ≥ 2.38 for evmone 0.24.0 (`install_evmone.sh` downloads the release binary, sha256-checked);
- disk: several GB (prestates and codes ~255 MB, plus the compilation artifacts of each run);
- for the semantic tests, to build the testrunner (`build_testrunner.sh`): cmake ≥ 3.13, a C++20 compiler (g++ 13 used),
  Boost ≥ 1.67 (1.83 used). It builds solidity's branch `testExpectationExtraction` (`cd4e61e8`) and evmone
  `94582ffd` (EVMC ABI 12; evmone ≥ 0.19 cannot be loaded).

## 3. The data: what is committed and how to regenerate it

Everything needed to evaluate a new configuration is committed except the RPC data (prestates and block hashes),
which is regenerated with
a free RPC. The steps below are those of `evaluation/scripts/run_mainnet_gas_evaluation.sh <step>`, run from the repository root.

### 3.1 Contract sources (Etherscan): `data/etherscan/`

`getsourcecode` for each contract: the original compiler input, the compiler version, the optimizer settings, the ABI
and the libraries.

    ETHERSCAN_API_KEY=... python3 evaluation/scripts/gas_mainnet_replay.py fetch-etherscan evaluation/data/inputs_most_called.txt

Existing files are kept. They give the contract names and ABIs (for the BigQuery buckets), the original inputs (to
reproduce the deployed code) and the library addresses.

### 3.2 Transaction sample (BigQuery): `data/mainnet/bigquery/sample_txs.json.gz`

The table `bigquery-public-data.crypto_ethereum.transactions`, filtered as follows:
- the ranking's period: 2021-01-01 to 2026-03-03, blocks 11,565,019 to 24,580,372;
- direct and successful transactions to each contract;
- per contract and function (ABI selector, plus `other`), the 25 with the smallest `FARM_FINGERPRINT(hash)` (20 are
  used), with the number of transactions per function for the frequency weights.

    BQ_PROJECT=<project> evaluation/scripts/run_mainnet_gas_evaluation.sh query dry-run   # regenerate the query; free estimate
    BQ_PROJECT=<project> evaluation/scripts/run_mainnet_gas_evaluation.sh run             # paid (asks first; CONFIRM=1 skips)
    BQ_PROJECT=<project> evaluation/scripts/run_mainnet_gas_evaluation.sh import          # table -> sample_txs.json.gz

The committed export makes these steps unnecessary. Then:

    evaluation/scripts/run_mainnet_gas_evaluation.sh sample load

These print the sample size and split the export per contract into `data/mainnet/txs/<address>.json.gz`.

### 3.3 Deployment data (Etherscan + Sourcify): `data/mainnet/deploy/`

- Etherscan `getcontractcreation`: the creator, the factory and the creation transaction.
- Sourcify v2: the compilation name, the constructor arguments and the immutable values. When the contract is not on
  Sourcify (22 contracts), Etherscan's constructor arguments are used.

    ETHERSCAN_API_KEY=... evaluation/scripts/run_mainnet_gas_evaluation.sh deploy

### 3.4 Prestates (RPC): `data/mainnet/txs/` and `codes/`, not committed

Per transaction, the RPC gives:
- the signed transaction, its receipt and its block header;
- its prestate (`debug_traceTransaction` with `prestateTracer`).

The codes are stored once each, by sha256. The step is resumable, and with a free rate-limited RPC it can take hours.

    evaluation/scripts/run_mainnet_gas_evaluation.sh prestate        # RPC_FILE=<file with an RPC URL> optional

### 3.5 Reproducing the deployed contracts: `resolve` and `immutables` (committed results)

    evaluation/scripts/run_mainnet_gas_evaluation.sh resolve immutables

- `resolve` handles the 22 contracts whose source comes from Etherscan:
  - it recompiles the original input with the original compiler and finds the on-chain code it matches: the address's
    own code, or the implementation of a proxy. Etherscan returns the implementation's source for minimal clones and
    ERC-1967 proxies;
  - it reads the immutable values from that code.
- `immutables` keys the on-chain immutable values by the AST ids of the corpus inputs:
  - when Sourcify's numbering differs, the values are read from the on-chain code and matched by declaration;
  - contracts using immutables of internal function type are marked to be excluded.

Both write into `deploy/` and `*_resolution.csv`.

### 3.6 Block hashes: `blockhashes` (after a first replay)

Some contracts read `BLOCKHASH` of blocks older than the parent: VRF proofs, Keeper registries, randomness. For the
transactions whose receipt check fails in a first replay, `blockhashes` traces the original locally (geth's `evm`),
fetches the hashes of the blocks it reads from the RPC, and stores them in `txs/`. The next replay then reproduces
those receipts. Run `replay report` again afterwards.

    evaluation/scripts/run_mainnet_gas_evaluation.sh blockhashes replay report

## 4. Running an evaluation

### 4.0 One command: the whole evaluation of a configuration

    GREY_FLAGS="<grey options>" SOLC=<solc version or binary> evaluation/scripts/evaluate.sh

For example:

    evaluation/scripts/evaluate.sh                                     # the default configuration (section 5)
    SOLC=examples/solc-without-opt evaluation/scripts/evaluate.sh      # both sides with solc-without-opt
    GREY_FLAGS="--split-critical-edges --hoist-return-labels" SOLC=0.8.37 FALLBACK_VERSION= evaluation/scripts/evaluate.sh

It runs every step below in order:
1. `setup`;
2. the RPC data if it is missing (`load prestate`);
3. `immutables`, then `compile codes replay report`;
4. `blockhashes`, and `replay report` again only if new hashes were fetched;
5. `diagnosis`, then `semantic` (skipped with `SKIP_SEMANTIC=1`).

It ends by printing the final results, also written to `final_results.txt` in the run's results folder:
- the configuration;
- the bytecode size of grey vs solc on the 1,000 contracts and on the semantic tests;
- the mainnet gas of grey vs solc, plainly and weighted by frequency;
- the mismatch classes, the number of unexplained mismatches and where every sampled transaction goes;
- the semantic test classes, including tests where grey fails and solc passes, and the gas of constructors and calls.

`evaluation/scripts/summarize_evaluation.py <results folder>` prints them again from a results folder.

The run's results folder is `data/mainnet/results/<RESULTS_NAME>`. By default the name is
`gas_<grey commit>_<solc>_<hash of the configuration>`; `-dirty` is added to the commit when `src/` has uncommitted
changes. Two configurations therefore never share cached codes. `run_mainnet_gas_evaluation.sh results-dir` prints the
folder of the current configuration.

### 4.1 Once: prepare the work machine

    export REMOTE=grey-remote REMOTE_DIR=grey_eval          # an ssh host; localhost works too
    evaluation/scripts/run_mainnet_gas_evaluation.sh setup

This copies the two corpora and writes their input lists (`inputs_most_called.txt`, `inputs_semantic.txt`). It also
copies `pyshim/` and the scripts. The solc binaries are downloaded into `$REMOTE_DIR/bin` the first time they are
needed.

### 4.2 Mainnet transactions

From the repository root, on the commit of grey to evaluate. The working tree's `src/` is copied to the work machine;
the copy is evaluated, and the working tree is never modified.

    evaluation/scripts/run_mainnet_gas_evaluation.sh compile codes replay report diagnosis

| step | where | what |
|---|---|---|
| `compile` | remote | `compile_variants.sh`: the 1,000 inputs with grey (artifacts: its assembly) and with solc (the reference), with the configuration of section 5 |
| `codes` | remote | the runtime code of each contract per variant: libraries linked, on-chain immutables written |
| `replay` | remote | evmone 0.24.0: receipt check under the block's fork, then original, solc and grey under Prague with the block gas limit |
| `report` | remote → local | gas totals, plain and weighted by function frequency; copied to `data/mainnet/results/<RESULTS_NAME>/` |
| `diagnosis` | remote → local | every mismatch with the original classified (gas-dependent, code-dependent, unexplained), and `accounting.txt`: where every sampled transaction goes |

The results go to `data/mainnet/results/<RESULTS_NAME>/` (section 4.0 for the default name).

With fresh RPC data, run `blockhashes replay report` after the first `report` (section 3.6).

### 4.3 Semantic tests

    evaluation/scripts/run_semantic_gas_evaluation.sh <work_dir> <grey src> <results dir> [jobs]        # on the work machine
    evaluation/scripts/run_mainnet_gas_evaluation.sh semantic                                           # or through the driver

This compiles the semantic tests at depths 16 and 8 (`SEMANTIC_DEPTHS`), with the same configuration. It builds the
testrunner the first time, then runs each test's trace with solc's and grey's creation codes. The outputs are:
- `<results>.log`: bytes per variant and gap with solc (`results/2026-10-04_semantic/bytes.txt` for the reference run);
- `<results>_semantic_d<depth>/summary.txt`: test classes (included, excluded, `variant_fails` = a bug, side effects,
  memory layout) and gas: constructor, code deposit, calls.

### 4.4 Reading the results

- `data/mainnet/results/<name>/summary.txt`:
  - the receipt check;
  - each variant's errors and mismatches;
  - over the transactions where every variant matches the original: `grey vs solc: plain ... gas (...%), weighted by
    frequency ...%; better / worse / equal`.
- `diagnosis/summary.txt` and `diagnosis/accounting.txt`: the class of every mismatch (section 4.5) and the category
  of every sampled transaction. Any `UNEXPLAINED` mismatch is a bug of a variant to investigate.
- `transactions.csv.gz`: one row per transaction and execution (receipt, original, each variant). It has the status,
  gas, matches and errors.

### 4.5 How the transactions are compared

- **Validity:** the original code is first executed under the fork of its own block, with its own gas limit. Its
  gas, status and logs must equal the receipt, which validates the prestate and the environment. Only valid
  transactions are used.
- **Executions:** the original, solc's and grey's codes are then executed from the same prestate under one fork for
  all, Prague, so that every transaction and variant runs under the same rules. The gas limit is raised to the
  block's, so that a slightly more expensive
  variant is measured instead of running out of gas. The variant's code replaces the contract's code at its address,
  or at the implementation for proxies, with the on-chain immutable values and linked libraries.
- **Matching:** a variant matches when its status, its logs (in order) and its resulting state equal the original's.
  The state comprises storage, nonces, and the codes of every account except the replaced one. The balances of the
  sender and the coinbase are ignored, as they depend on the gas.
- **Gas:** compared over the transactions where every variant matches the original. It is the transaction's
  `gasUsed`. Results are given plainly, and weighted by frequency: each transaction weighs the transactions of its
  function in the period divided by those sampled from it.
- **Classes of the diagnosis:** every transaction where a variant does not match is executed again with traces.
  - **gas-dependent:** the original itself changes the same values when only its gas consumption changes (warm access
    list, own gas limit), or the change equals a difference of `GAS` readings (refunds, fees, loops bounded by the
    remaining gas);
  - **code-dependent:** the values are the code size or hash, or come from contracts created, or CREATE2 addresses
    predicted, from initcode embedded in the code;
  - **excluded** before the comparison: immutables of internal function type (compiler-specific values), proxies
    running another implementation than the verified source, an address without code when the transaction ran;
  - **unexplained:** anything else.

  Gas- and code-dependent mismatches appear with any recompilation, so they are not errors of a variant.

## 5. Configuring the compared code

`evaluate.sh` and `run_mainnet_gas_evaluation.sh` take the configuration from the environment. They pass it to
`compile_variants.sh`, `codes`, `immutables` and `semantic`. The defaults are the evaluated configuration:

| variable | default | meaning |
|---|---|---|
| `SOLC` | `0.8.35` | the solc of both sides: Yul CFG and assembly importer for grey, and solc's reference compilation. An official version is downloaded (sha256-checked) on the work machine. A path to a local binary (e.g. `examples/solc-without-opt`, without the legacy optimizer) is copied there |
| `FALLBACK_VERSION` | `0.8.37` | official solc that generates the Yul CFG when `SOLC` fails there with an internal error; empty: none |
| `GREY_FLAGS` | `--split-critical-edges --hoist-return-labels --cse --prune-unused-arguments --combine-functions --reinline-after-merge --thread-empty-blocks --call-convention orders` | grey's options; `--debug` is always added |
| `PROPAGATION` | `off` | grey's constant propagation (`off`: `decide_if_propagated` returns False in the evaluated copy) |
| `DEPTH` | `16` | maximum stack depth reachable by DUP/SWAP |

The grey version is the working tree's `src/`: check out the branch or commit to evaluate. solc's side is the corpus
input compiled via-IR with the optimizer enabled. `runs` comes from the input (200), and the metadata is disabled.

| `SEMANTIC_DEPTHS` | `16,8` | depths of the semantic tests |

The steps can also be run one by one with the same variables, e.g.:

    GREY_FLAGS="--split-critical-edges --hoist-return-labels" \
        evaluation/scripts/run_mainnet_gas_evaluation.sh immutables compile codes replay report diagnosis

`immutables` runs for each configuration: the AST ids of the corpus inputs are taken from the parser of `SOLC`. It
rewrites `data/mainnet/deploy/`, which only changes when another solc numbers the declarations differently.
