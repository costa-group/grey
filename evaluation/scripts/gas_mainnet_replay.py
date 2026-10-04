#!/usr/bin/env python3
"""
Gas and correctness of grey vs solc on real mainnet transactions of the 1k most-called contracts, replayed with
anvil (foundry) on a fork of mainnet in which the code of the contract is replaced by each variant's.

Stages (the data of the first two is stored in <data_dir> and committed, so the experiment can be repeated without
downloading it again; the historical state is immutable, so the replay only needs an archive RPC):
  fetch-txs <addresses> <data_dir> --end-block B [--per-contract K] [--window W]
      Etherscan V2 txlist (key in $ETHERSCAN_API_KEY) of the blocks (B-W, B]; keeps K successful direct calls per
      contract (to == address, non-empty calldata), round-robin over the function selectors, newest first. Then the
      full transaction, the receipt and the header of its block from the RPC. Writes txs/<address>.json.gz.
  fetch-deploy <addresses> <data_dir>
      Sourcify v2 (deployer, creation transaction, constructor arguments, immutables); fallback: Etherscan
      getcontractcreation + ConstructorArguments of evaluation/data/etherscan/<address>.json.
      Writes deploy/<address>.json.gz.
  load-bigquery <export files> <data_dir>
      Alternative to fetch-txs: splits the export of evaluation/scripts/bigquery/sample_txs.sql (NDJSON, possibly
      gzipped) into txs/<address>.json.gz (the RPC part of fetch-txs is still needed: run fetch-txs --from-cache).
  replay <data_dir> <results_dir> --inputs-from F --solc S --variant NAME=ARTIFACT ... --out-dir D
      For each transaction (block n): anvil forks at n-1 with block n's timestamp, base fee and coinbase; the
      original transaction is sent from its sender (impersonated) and kept only if gasUsed and status equal the
      receipt. For each variant, from the same snapshot: the runtime code is obtained by executing its creation
      code + constructor arguments from the deployer (eth_call), the deployment is also mined once to measure its
      gas, the code is set at the address and the transaction is replayed. Status, logs and the returned data must
      equal the original's. The own-code gas is the gas of the frames that execute the address (callTracer), minus
      their subcalls (the top frame also minus the intrinsic gas).
  report <out_dir>
      Totals over the transactions validated for every variant.

Usage (from ~/grey_eval on grey-remote; RPC with archive state, e.g. https://eth.drpc.org):
    python3 evaluation/scripts/gas_mainnet_replay.py replay ../repo/examples/most_called_0_8/gas_data results/thread_most_called \
        --inputs-from inputs_most_called.txt --solc bin/solc-0.8.35 --variant solc=solc_solc --variant grey=thread \
        --rpc https://eth.drpc.org --out-dir gas/mainnet [--jobs N]
"""

import argparse
import gzip
import itertools
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd

from gas_common import (NotEnoughDiskSpace, ensure_free_space, input_info_for, intrinsic_calldata_gas, jobs_from_load,
                        patch_immutables, variant_creation_codes, variant_immutable_references)

ETHERSCAN_API = "https://api.etherscan.io/v2/api"
SOURCIFY_API = "https://sourcify.dev/server/v2/contract/1"
# The contracts' sources, settings and ABIs from Etherscan (getsourcecode), and the corpus of compiler inputs. Relative
# to the evaluation folder (evaluation/scripts/..), or given by the environment (e.g. on grey-remote)
EVALUATION_FOLDER = Path(__file__).resolve().parent.parent
ETHERSCAN_FOLDER = Path(os.environ.get("ETHERSCAN_FOLDER", EVALUATION_FOLDER.joinpath("data", "etherscan")))
CORPUS_FOLDER = Path(os.environ.get("CORPUS_FOLDER", EVALUATION_FOLDER.parent.joinpath(
    "examples", "most_called_0_8", "test_most_called")))
ADDRESS_PATTERN = re.compile(r"0x[0-9a-fA-F]{40}")
ORIGINAL = "original"


# ---------------------------------------------------------------- I/O helpers

def write_json_gz(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt") as f:
        json.dump(data, f, sort_keys=True)


def read_json_gz(path: Path):
    with gzip.open(path, "rt") as f:
        return json.load(f)


def http_json(url: str, payload: Optional[Dict] = None, retries: int = 5, timeout: float = 60):
    """
    GET (payload None) or POST of JSON, with retries and exponential backoff on network errors and HTTP 429/5xx
    """
    data = None if payload is None else json.dumps(payload).encode()
    headers = {"Content-Type": "application/json", "User-Agent": "grey-gas-evaluation"}
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            if attempt == retries - 1 or error.code not in (408, 429, 500, 502, 503, 504):
                raise
            if error.code == 429:
                # Rate limited: the time the server asks for, or a long backoff
                retry_after = error.headers.get("Retry-After")
                time.sleep(float(retry_after) if retry_after and retry_after.isdigit() else 10 * (attempt + 1))
                continue
        except (urllib.error.URLError, socket.timeout, ConnectionError):
            if attempt == retries - 1:
                raise
        time.sleep(2 ** attempt)


class JsonRpc:
    """
    Minimal JSON-RPC client
    """

    def __init__(self, url: str):
        self.url, self.identifier = url, 0

    def __call__(self, method: str, *params):
        self.identifier += 1
        answer = http_json(self.url, {"jsonrpc": "2.0", "id": self.identifier, "method": method, "params": list(params)})
        if "error" in answer:
            raise RuntimeError(f"{method}: {answer['error']}")
        return answer["result"]


def read_addresses(addresses_file: Path) -> List[str]:
    """
    Addresses (lower case, in order, without duplicates) of a file: one per line, or paths that contain them
    (e.g. inputs_most_called.txt)
    """
    addresses = []
    for line in addresses_file.read_text().splitlines():
        match = ADDRESS_PATTERN.search(line)
        if match:
            addresses.append(match.group(0).lower())
    return list(dict.fromkeys(addresses))


def etherscan(params: Dict) -> Dict:
    """
    Etherscan V2 call (chain 1), respecting the free-tier limit (5 calls per second)
    """
    api_key = os.environ.get("ETHERSCAN_API_KEY")
    assert api_key, "Set ETHERSCAN_API_KEY"
    query = "&".join(f"{key}={value}" for key, value in {"chainid": 1, **params, "apikey": api_key}.items())
    time.sleep(0.22)
    return http_json(f"{ETHERSCAN_API}?{query}")


# ---------------------------------------------------------------- fetch-etherscan

def fetch_etherscan(args) -> None:
    """
    The verified source of each contract from Etherscan (getsourcecode): its original compiler input (SourceCode, a
    standard JSON wrapped in '{{ }}' or a single file), CompilerVersion, optimizer settings, ABI, Library, proxy
    information. Stored as <etherscan_dir>/<address>.json (the first result of the call); existing files are kept
    """
    args.etherscan_dir.mkdir(parents=True, exist_ok=True)
    for address in read_addresses(args.addresses):
        target = args.etherscan_dir.joinpath(f"{address}.json")
        if target.is_file():
            continue
        answer = etherscan({"module": "contract", "action": "getsourcecode", "address": address})
        result = (answer.get("result") or [None])[0]
        if not isinstance(result, dict) or not result.get("SourceCode"):
            print(f"{address}: no verified source ({str(answer.get('result'))[:80]})", flush=True)
            continue
        target.write_text(json.dumps(result, indent=1))
        print(f"{address}: {result.get('ContractName')} {result.get('CompilerVersion')}", flush=True)


# ---------------------------------------------------------------- fetch-txs

def select_transactions(transactions: List[Dict], address: str, per_contract: int) -> List[Dict]:
    """
    Successful direct calls to the address with calldata, round-robin over the selectors (each selector newest
    first, selectors ordered by their newest call), at most per_contract
    """
    candidates = [transaction for transaction in transactions
                  if transaction.get("to", "").lower() == address and transaction.get("isError") == "0"
                  and transaction.get("txreceipt_status", "1") == "1" and len(transaction.get("input", "")) >= 10]
    candidates.sort(key=lambda transaction: (-int(transaction["blockNumber"]), -int(transaction["transactionIndex"])))
    by_selector: Dict[str, List[Dict]] = defaultdict(list)
    for transaction in candidates:
        by_selector[transaction["input"][:10]].append(transaction)
    selected = []
    for round_transactions in itertools.zip_longest(*by_selector.values()):
        selected.extend(transaction for transaction in round_transactions if transaction is not None)
        if len(selected) >= per_contract:
            break
    return selected[:per_contract]


# First block of Shanghai: the earliest block of the RPC-based replay (older transactions are not sampled there)
SHANGHAI_BLOCK = 17_034_870


def sample_per_selector(transactions: List[Dict], address: str, per_selector: int) -> List[Dict]:
    """
    Successful direct calls to the address, at most per_selector per selector ('nodata' for calls without one), in a
    deterministic random order (sha256 of the hash), like the BigQuery sample
    """
    import hashlib
    candidates = [transaction for transaction in transactions
                  if transaction.get("to", "").lower() == address and transaction.get("isError") == "0"
                  and transaction.get("txreceipt_status", "1") == "1"]
    by_selector: Dict[str, List[Dict]] = defaultdict(list)
    for transaction in sorted(candidates, key=lambda t: hashlib.sha256(t["hash"].encode()).hexdigest()):
        selector = transaction["input"][:10] if len(transaction.get("input", "")) >= 10 else "nodata"
        if len(by_selector[selector]) < per_selector:
            by_selector[selector].append({**transaction, "bucket": selector})
    return [transaction for selector in sorted(by_selector) for transaction in by_selector[selector]]


def addresses_missing_from_export(addresses: List[str], export_files: List[Path]) -> List[str]:
    present = {row["target"].lower() for row in read_bigquery_export(export_files)}
    return [address for address in addresses if address not in present]


def complete_from_rpc(rpc: JsonRpc, hashes: Iterable[str], block_cache: Dict[int, Dict]) -> List[Dict]:
    """
    The full transaction, receipt and block header of each hash (the data needed to replay it)
    """
    completed = []
    for transaction_hash in hashes:
        transaction = rpc("eth_getTransactionByHash", transaction_hash)
        receipt = rpc("eth_getTransactionReceipt", transaction_hash)
        block_number = int(transaction["blockNumber"], 16)
        if block_number not in block_cache:
            header = rpc("eth_getBlockByNumber", hex(block_number), False)
            header.pop("transactions", None)
            block_cache[block_number] = header
        receipt.pop("logsBloom", None)
        completed.append({"transaction": transaction, "receipt": receipt, "block": block_cache[block_number]})
    return completed


def fetch_txs(args) -> None:
    rpc = JsonRpc(args.rpc)
    block_cache: Dict[int, Dict] = {}
    addresses = read_addresses(args.addresses)
    if args.missing_from:
        addresses = addresses_missing_from_export(addresses, args.missing_from)
        print(f"{len(addresses)} contracts without transactions in the BigQuery export", flush=True)
    for address in addresses:
        output_file = args.data_dir.joinpath("txs", f"{address}.json.gz")
        if output_file.is_file() and not args.from_cache:
            continue
        if args.from_cache:
            if not output_file.is_file():
                continue
            stored = read_json_gz(output_file)
            if stored.get("replay_data") is not None:
                continue
            selected_hashes = [transaction["hash"] for transaction in stored["selected"]]
            metadata = {key: value for key, value in stored.items() if key != "replay_data"}
        elif args.missing_from:
            # Going back from the end block in widening windows (never before Shanghai) until a window has
            # transactions; at most 10,000 per query (Etherscan), sampled per selector at random
            transactions, window = [], args.window
            while True:
                start_block = max(SHANGHAI_BLOCK, args.end_block - window + 1)
                answer = etherscan({"module": "account", "action": "txlist", "address": address,
                                    "startblock": start_block, "endblock": args.end_block,
                                    "page": 1, "offset": 10000, "sort": "desc"})
                transactions = answer.get("result") if isinstance(answer.get("result"), list) else []
                selected = sample_per_selector(transactions, address, args.per_selector)
                if selected or start_block == SHANGHAI_BLOCK:
                    break
                window *= 4
        else:
            # Contracts without calls in the window: wider windows (10x, 40x), newest first
            for window in (args.window, 10 * args.window, 40 * args.window):
                answer = etherscan({"module": "account", "action": "txlist", "address": address,
                                    "startblock": max(0, args.end_block - window + 1), "endblock": args.end_block,
                                    "page": 1, "offset": 1000, "sort": "desc"})
                transactions = answer.get("result") if isinstance(answer.get("result"), list) else []
                selected = select_transactions(transactions, address, args.per_contract)
                if selected:
                    break
        if not args.from_cache:
            selected_hashes = [transaction["hash"] for transaction in selected]
            metadata = {"address": address, "source": "etherscan txlist", "end_block": args.end_block,
                        "window": window, "per_contract": args.per_contract, "per_selector": args.per_selector,
                        "candidates": len(transactions),
                        "selected": [{key: transaction[key] for key in ("hash", "blockNumber", "functionName", "bucket")
                                      if key in transaction} for transaction in selected]}
        replay_data = complete_from_rpc(rpc, selected_hashes, block_cache)
        write_json_gz(output_file, {**metadata, "replay_data": replay_data})
        print(f"{address}: {len(replay_data)} transactions", flush=True)


# ---------------------------------------------------------------- load-bigquery

def read_bigquery_export(export_files: List[Path]) -> List[Dict]:
    """
    Rows of the export of evaluation/scripts/bigquery/sample_txs.sql (NDJSON, possibly gzipped): one per (target, bucket)
    with the approximate number of transactions and the sample (tx_hash, block_number, depth, call_type) in random order
    """
    rows = []
    for export_file in export_files:
        opener = gzip.open if export_file.suffix == ".gz" else open
        with opener(export_file, "rt") as f:
            rows.extend(json.loads(line) for line in f if line.strip())
    return rows


def effective_buckets(rows: List[Dict], min_raw_transactions: int) -> List[Dict]:
    """
    The buckets of the export after merging the noise of the contracts whose ABI has no functions (bucketed by raw
    selector in BigQuery): a raw selector with fewer than min_raw_transactions transactions in the period is not a
    function (e.g. a bot whose calldata starts with data: 0x57b8792c... had 166,200 distinct selectors), so it is
    merged into the contract's 'other' bucket. The samples of the merged buckets are joined in a deterministic random
    order (sha256 of the hash; BigQuery's FARM_FINGERPRINT is not available locally)
    """
    import hashlib
    without_abi = {row["target"].lower() for row in rows if not abi_selectors(row["target"].lower())}
    kept, merged = [], defaultdict(list)
    for row in rows:
        target = row["target"].lower()
        if target in without_abi and row["bucket"] not in ("nodata", "other") and \
                int(row["transactions"]) < min_raw_transactions:
            merged[target].append(row)
        else:
            kept.append({**row, "target": target})
    for target, merged_rows in merged.items():
        sample = sorted((entry for row in merged_rows for entry in row["sample"]),
                        key=lambda entry: hashlib.sha256(entry["tx_hash"].encode()).hexdigest())
        kept.append({"target": target, "bucket": "other", "merged_selectors": len(merged_rows),
                     "transactions": str(sum(int(row["transactions"]) for row in merged_rows)),
                     "frames": str(sum(int(row["frames"]) for row in merged_rows)),
                     "direct_frames": str(sum(int(row["direct_frames"]) for row in merged_rows)),
                     "sample": sample})
    return kept


def load_bigquery(args) -> None:
    """
    Splits the BigQuery export per target: per bucket, the first per_bucket transactions of its random order that
    were not already selected for that target (a transaction can execute several functions of the same contract).
    The RPC data is added afterwards with fetch-txs --from-cache. The bucket counts are kept to weight the results
    """
    per_target: Dict[str, List[Dict]] = defaultdict(list)
    for row in effective_buckets(read_bigquery_export(args.export_files), args.min_raw_transactions):
        per_target[row["target"]].append(row)
    total = 0
    for target, rows in sorted(per_target.items()):
        selected, seen = [], set()
        for row in sorted(rows, key=lambda row: row["bucket"]):
            taken = 0
            for entry in row["sample"]:
                if taken == args.per_bucket:
                    break
                if entry["tx_hash"] in seen:
                    continue
                seen.add(entry["tx_hash"])
                taken += 1
                selected.append({"hash": entry["tx_hash"], "blockNumber": str(entry["block_number"]),
                                 "bucket": row["bucket"], "depth": entry["depth"], "call_type": entry["call_type"]})
        buckets = {row["bucket"]: {"transactions": int(row["transactions"]), "frames": int(row["frames"]),
                                   "direct_frames": int(row["direct_frames"])} for row in rows}
        total += len(selected)
        write_json_gz(args.data_dir.joinpath("txs", f"{target}.json.gz"),
                      {"address": target, "source": "bigquery sample_txs.sql", "per_bucket": args.per_bucket,
                       "buckets": buckets, "selected": selected, "replay_data": None})
    print(f"{len(per_target)} targets, {total} transactions")


def import_bigquery_json(args) -> None:
    """
    Converts the result table read with `bq --format=json head -n N <table>` (a JSON array) into the gzipped NDJSON
    the other stages read, sorted by target and bucket so that the file is deterministic
    """
    rows = json.loads(args.bq_json.read_text())
    if args.expected_rows is not None and len(rows) != args.expected_rows:
        sys.exit(f"{len(rows)} rows read but the table has {args.expected_rows}: increase -n of bq head")
    rows.sort(key=lambda row: (row["target"], row["bucket"]))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(args.output, "wt") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")
    print(f"{args.output}: {len(rows)} rows")


# ---------------------------------------------------------------- sample-size

def abi_selectors(address: str) -> Optional[set]:
    """
    Function selectors of the contract's ABI (evaluation/data/etherscan/<address>.json), None if unknown.
    Needs pycryptodome (keccak-256)
    """
    from Crypto.Hash import keccak

    def canonical_type(parameter: Dict) -> str:
        kind = parameter["type"]
        if kind.startswith("tuple"):
            return "(" + ",".join(canonical_type(component) for component in parameter["components"]) + ")" + \
                kind[len("tuple"):]
        return kind

    etherscan_file = ETHERSCAN_FOLDER.joinpath(f"{address}.json")
    if not etherscan_file.is_file():
        return None
    try:
        abi = json.loads(json.loads(etherscan_file.read_text())["ABI"])
    except (KeyError, ValueError):
        return None
    selectors = set()
    for entry in abi:
        if entry.get("type") == "function":
            signature = f"{entry['name']}({','.join(canonical_type(p) for p in entry.get('inputs', []))})"
            selectors.add("0x" + keccak.new(digest_bits=256, data=signature.encode()).hexdigest()[:8])
    return selectors


def sample_size(args) -> None:
    """
    Size of the sample that load-bigquery would select from the export (per_bucket per (contract, bucket)), and the
    contracts of the list without any transaction in the window
    """
    rows = effective_buckets(read_bigquery_export(args.export_files), args.min_raw_transactions)
    frame = pd.DataFrame([{"target": row["target"].lower(), "bucket": row["bucket"],
                           "transactions": int(row["transactions"]), "sampled": min(args.per_bucket, len(row["sample"]))}
                          for row in rows])
    per_contract = frame.groupby("target").sampled.sum()
    missing = [address for address in read_addresses(args.addresses) if address not in set(frame.target)]
    print(f"{frame.target.nunique()} contracts with transactions, {len(missing)} without any in the window; "
          f"{len(frame)} buckets ({int((frame.bucket == 'other').sum())} 'other')\n"
          f"transactions in the window (approximate) {int(frame.transactions.sum()):,}; sample (upper bound, before "
          f"removing duplicates across buckets) {int(frame.sampled.sum()):,}\n"
          f"per contract: median {per_contract.median():.0f}, p90 {per_contract.quantile(0.9):.0f}, max "
          f"{per_contract.max():.0f} ({per_contract.idxmax()})")
    if missing:
        print("contracts without transactions (candidates for Etherscan's txlist over the whole history):")
        print("\n".join(f"  {address}" for address in missing))


BIGQUERY_QUERY_HEADER = """-- One scan of BigQuery that both counts and samples the transactions executing code of the 1k most-called
-- contracts (evaluation/data/inputs_most_called.txt), for evaluation/scripts/gas_mainnet_replay.py.
-- Generated by `gas_mainnet_replay.py make-bigquery-query`; do not edit by hand."""


def make_bigquery_query(args) -> None:
    """
    Regenerates evaluation/scripts/bigquery/sample_txs.sql from the template (the same file, between the markers) with the
    ABI selectors of the contracts of the list
    """
    template = args.template.read_text()
    begin, finish = "    -- BEGIN TARGETS\n", "    -- END TARGETS\n"
    head, rest = template.split(begin, 1)
    _, tail = rest.split(finish, 1)
    entries = []
    for address in read_addresses(args.addresses):
        selectors = sorted(abi_selectors(address) or [])
        listed = ", ".join(f"'{selector}'" for selector in selectors)
        entries.append(f"STRUCT('{address}' AS address, ARRAY<STRING>[{listed}] AS selectors)")
    args.output.write_text(head + begin + "    " + ",\n    ".join(entries) + "\n" + finish + tail)
    print(f"{args.output}: {len(entries)} contracts, {args.output.stat().st_size / 1024:.0f} KB (BigQuery limit 1 MB)")


# ---------------------------------------------------------------- fetch-deploy

def fetch_deploy(args) -> None:
    """
    Per contract: the creator (Etherscan getcontractcreation: the factory if it was created by a contract, else the
    sender of the creation transaction) and the nonce it had then (the creation transaction's nonce, or the
    factory's nonce before the creation block, from the RPC); the constructor arguments and immutables (Sourcify v2,
    falling back to the ConstructorArguments of evaluation/data/etherscan/<address>.json)
    """
    rpc = JsonRpc(args.rpc)
    pending = [address for address in read_addresses(args.addresses)
               if not args.data_dir.joinpath("deploy", f"{address}.json.gz").is_file()]
    for start in range(0, len(pending), 5):
        chunk = pending[start:start + 5]
        answer = etherscan({"module": "contract", "action": "getcontractcreation",
                            "contractaddresses": ",".join(chunk)})
        creations = {entry["contractAddress"].lower(): entry for entry in answer.get("result") or []
                     if isinstance(entry, dict)}
        for address in chunk:
            if address not in creations:
                print(f"{address}: no creation information", flush=True)
                continue
            creation = creations[address]
            factory = (creation.get("contractFactory") or "").lower()
            creator = creation["contractCreator"].lower()
            creation_block = int(creation["blockNumber"])
            if factory:
                creation_nonce = rpc("eth_getTransactionCount", factory, hex(creation_block - 1))
            else:
                creation_nonce = rpc("eth_getTransactionByHash", creation["txHash"])["nonce"]
            deploy_info = {"address": address, "deployer": factory or creator, "creation_sender": creator,
                           "factory": factory or None, "creation_transaction": creation["txHash"],
                           "creation_block": creation_block, "creation_nonce": creation_nonce,
                           "constructor_arguments": None, "immutables": {}, "contract": None}
            # Sourcify rate-limits bursts (HTTP 429)
            time.sleep(0.5)
            sourcify = http_json(f"{SOURCIFY_API}/{address}?fields=creationBytecode.transformationValues,"
                                 f"runtimeBytecode.transformationValues,compilation.name", retries=10)
            if sourcify and sourcify.get("compilation"):
                creation_values = sourcify.get("creationBytecode", {}).get("transformationValues") or {}
                runtime_values = sourcify.get("runtimeBytecode", {}).get("transformationValues") or {}
                deploy_info.update(source="sourcify", contract=sourcify["compilation"].get("name"),
                                   constructor_arguments=creation_values.get("constructorArguments") or "0x",
                                   immutables=runtime_values.get("immutables") or {})
            else:
                etherscan_file = ETHERSCAN_FOLDER.joinpath(f"{address}.json")
                source_info = json.loads(etherscan_file.read_text()) if etherscan_file.is_file() else {}
                arguments = source_info.get("ConstructorArguments") or ""
                deploy_info.update(source="etherscan", contract=source_info.get("ContractName"),
                                   constructor_arguments="0x" + arguments.removeprefix("0x"))
            write_json_gz(args.data_dir.joinpath("deploy", f"{address}.json.gz"), deploy_info)
            print(f"{address}: {deploy_info['source']}, deployer {deploy_info['deployer']}"
                  f"{' (factory)' if factory else ''}", flush=True)


# ---------------------------------------------------------------- fetch-prestate

def store_code(codes_dir: Path, code: str) -> str:
    """
    Stores a contract code once (codes/<sha256 of the hex>.hex.gz) and returns its reference "sha256:<digest>"
    """
    import hashlib
    digest = hashlib.sha256(code.encode()).hexdigest()
    code_file = codes_dir.joinpath(f"{digest}.hex.gz")
    if not code_file.is_file():
        codes_dir.mkdir(parents=True, exist_ok=True)
        temporary = code_file.with_suffix(f".tmp{os.getpid()}")
        with gzip.open(temporary, "wt") as f:
            f.write(code)
        temporary.replace(code_file)
    return f"sha256:{digest}"


def fetch_transaction_prestate(rpc: JsonRpc, transaction_hash: str, codes_dir: Path,
                               block_cache: Dict[int, Dict]) -> Dict:
    """
    What the offline replay of a transaction needs: the signed transaction, its receipt (without the bloom), the
    header of its block and its prestate (the accounts and storage slots it reads, as they were right before it,
    i.e. after the earlier transactions of its block), with the codes replaced by references to codes_dir
    """
    transaction = rpc("eth_getTransactionByHash", transaction_hash)
    receipt = rpc("eth_getTransactionReceipt", transaction_hash)
    receipt.pop("logsBloom", None)
    block_number = int(transaction["blockNumber"], 16)
    if block_number not in block_cache:
        header = rpc("eth_getBlockByNumber", hex(block_number), False)
        header.pop("transactions", None)
        header.pop("logsBloom", None)
        block_cache[block_number] = header
    prestate = rpc("debug_traceTransaction", transaction_hash, {"tracer": "prestateTracer", "timeout": "60s"})
    for account in prestate.values():
        if account.get("code") not in (None, "0x"):
            account["code"] = store_code(codes_dir, account["code"])
    return {"transaction": transaction, "receipt": receipt, "block": block_cache[block_number], "prestate": prestate}


def fetch_contract_prestates(txs_file: Path, codes_dir: Path, rpc_url: str, requests_per_second: float) \
        -> Tuple[str, int, int]:
    """
    Fetches the prestate data of the selected transactions of one contract that are not stored yet (resumable: the
    file is rewritten every 20 transactions). Returns the address, the transactions stored and the errors
    """
    rpc = JsonRpc(rpc_url)
    stored = read_json_gz(txs_file)
    replay_data = {entry["transaction"]["hash"]: entry for entry in stored.get("prestate_data") or []}
    errors = dict(stored.get("prestate_errors") or {})
    block_cache: Dict[int, Dict] = {}
    pending = [entry["hash"] for entry in stored["selected"] if entry["hash"] not in replay_data]
    minimum_interval = 4 / requests_per_second if requests_per_second > 0 else 0
    for index, transaction_hash in enumerate(pending, 1):
        started = time.time()
        try:
            replay_data[transaction_hash] = fetch_transaction_prestate(rpc, transaction_hash, codes_dir, block_cache)
            errors.pop(transaction_hash, None)
        except Exception as exception:
            errors[transaction_hash] = f"{type(exception).__name__}: {str(exception)[:300]}"
        if index % 20 == 0 or index == len(pending):
            write_json_gz(txs_file, {**stored, "prestate_data": list(replay_data.values()), "prestate_errors": errors})
        # About 4 requests per transaction (fewer when the header is cached)
        time.sleep(max(0.0, minimum_interval - (time.time() - started)))
    return stored["address"], len(replay_data), len(errors)


def fetch_prestate(args) -> None:
    """
    Prestate data of every selected transaction, for the offline replay. Contracts are processed in parallel; the
    total rate of requests is shared among the jobs
    """
    txs_files = sorted(args.data_dir.joinpath("txs").glob("*.json.gz"))
    txs_files = txs_files[:args.limit] if args.limit else txs_files
    codes_dir = args.data_dir.joinpath("codes")
    jobs = args.jobs or jobs_from_load()
    per_job_rate = args.requests_per_second / jobs
    print(f"{len(txs_files)} contracts, {jobs} jobs, {args.requests_per_second} requests/s in total", flush=True)
    done = errors = 0
    with ProcessPoolExecutor(max_workers=jobs) as executor:
        futures = [executor.submit(fetch_contract_prestates, txs_file, codes_dir, args.rpc, per_job_rate)
                   for txs_file in txs_files]
        for index, future in enumerate(futures, 1):
            address, stored, failed = future.result()
            done += stored
            errors += failed
            if index % 20 == 0 or index == len(futures):
                print(f"{index} / {len(futures)} contracts, {done} transactions stored, {errors} errors", flush=True)
                try:
                    ensure_free_space(args.data_dir, args.min_free_gb)
                except NotEnoughDiskSpace as exception:
                    print(f"Stopping: {exception}", flush=True)
                    for pending in futures:
                        pending.cancel()
                    break


# ---------------------------------------------------------------- replay

class RpcProxy:
    """
    Local HTTP proxy that forwards JSON-RPC requests to the upstream URL and counts them. anvil only sees the local
    URL: the upstream one may contain an API key, and both the arguments of a process (ps) and anvil's fork
    configuration (anvil_nodeInfo, served on localhost) are visible to the other users of the machine
    """

    def __init__(self, upstream_url: str):
        import http.server
        import threading
        proxy = self
        self.requests = 0

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                proxy.requests += 1
                request = urllib.request.Request(upstream_url, data=body, headers={
                    "Content-Type": "application/json", "User-Agent": "grey-gas-evaluation"})
                try:
                    with urllib.request.urlopen(request, timeout=120) as response:
                        status, answer = response.status, response.read()
                except urllib.error.HTTPError as error:
                    status, answer = error.code, error.read()
                except (urllib.error.URLError, socket.timeout, ConnectionError) as error:
                    status, answer = 502, str(error).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(answer)))
                self.end_headers()
                self.wfile.write(answer)

            def log_message(self, *_):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


class Anvil:
    """
    An anvil process on a free port, forked through a local RpcProxy (re-forked per transaction with anvil_reset)
    """

    def __init__(self, anvil_binary: str, rpc_url: str, compute_units: int):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            self.port = probe.getsockname()[1]
        self.proxy = RpcProxy(rpc_url)
        self.rpc_url = self.proxy.url
        # No storage caching (disk), automatic impersonation of every sender, the chain id of mainnet
        self.process = subprocess.Popen(
            [anvil_binary, "--port", str(self.port), "--fork-url", self.rpc_url, "--no-storage-caching",
             "--auto-impersonate", "--accounts", "1", "--chain-id", "1", "--compute-units-per-second", str(compute_units),
             "--retries", "10", "--timeout", "120000", "--silent"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.rpc = JsonRpc(f"http://127.0.0.1:{self.port}")
        for _ in range(120):
            try:
                self.rpc("eth_chainId")
                return
            except Exception:
                time.sleep(0.5)
        raise RuntimeError("anvil did not start")

    def close(self):
        self.process.terminate()
        self.process.wait(timeout=30)
        self.proxy.close()

    def fork(self, block_number: int, next_block: Dict) -> None:
        """
        State at the end of block_number; the next mined block gets next_block's timestamp, base fee and coinbase
        """
        self.rpc("anvil_reset", {"forking": {"jsonRpcUrl": self.rpc_url, "blockNumber": block_number}})
        self.prepare_next_block(next_block)

    def prepare_next_block(self, next_block: Dict) -> None:
        self.rpc("evm_setNextBlockTimestamp", int(next_block["timestamp"], 16))
        self.rpc("anvil_setNextBlockBaseFeePerGas", next_block["baseFeePerGas"])
        self.rpc("anvil_setCoinbase", next_block["miner"])

    def wait_receipt(self, transaction_hash: str, timeout: float = 900) -> Dict:
        """
        Receipt of a sent transaction. Automine mines it asynchronously, and the execution may take long, since the
        state of the fork is fetched lazily from the RPC
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            receipt = self.rpc("eth_getTransactionReceipt", transaction_hash)
            if receipt is not None:
                return receipt
            time.sleep(0.5)
        raise TimeoutError(f"transaction {transaction_hash} not mined in {timeout} s")

    def snapshot(self) -> str:
        return self.rpc("evm_snapshot")

    def restart_from(self, snapshot: str, next_block: Dict) -> str:
        """
        Reverts to the snapshot (consumed by anvil), takes a new one and prepares the next block again (the settings
        of the next block are not part of the snapshot)
        """
        assert self.rpc("evm_revert", snapshot), "evm_revert failed"
        new_snapshot = self.snapshot()
        self.prepare_next_block(next_block)
        return new_snapshot


def transaction_request(transaction: Dict) -> Dict:
    """
    eth_sendTransaction parameters reproducing an original transaction (sender impersonated)
    """
    request = {"from": transaction["from"], "to": transaction["to"], "input": transaction["input"],
               "value": transaction["value"], "gas": transaction["gas"], "nonce": transaction["nonce"]}
    if transaction.get("maxFeePerGas") is not None:
        request.update(maxFeePerGas=transaction["maxFeePerGas"],
                       maxPriorityFeePerGas=transaction["maxPriorityFeePerGas"])
    else:
        request["gasPrice"] = transaction["gasPrice"]
    if transaction.get("accessList"):
        request["accessList"] = transaction["accessList"]
    return request


def own_code_gas(frame: Dict, address: str, top_level_intrinsic: int, is_top: bool = True) -> int:
    """
    Gas of the frames of a callTracer trace that execute the code at address (CALL/STATICCALL to it, or
    DELEGATECALL/CALLCODE whose code address is it), minus their subcalls. The top frame's gasUsed includes the
    intrinsic gas of the transaction, which is subtracted
    """
    children = frame.get("calls") or []
    total = sum(own_code_gas(child, address, 0, False) for child in children)
    if frame.get("to", "").lower() == address and frame.get("type") != "CREATE":
        own = int(frame["gasUsed"], 16) - sum(int(child["gasUsed"], 16) for child in children)
        total += own - (top_level_intrinsic if is_top else 0)
    return total


def normalized_logs(receipt: Dict) -> List[Tuple]:
    return [(log["address"].lower(), tuple(log["topics"]), log["data"]) for log in receipt["logs"]]


def execute_transaction(anvil: Anvil, transaction: Dict, address: str, intrinsic: int) -> Dict:
    """
    Sends the transaction (mined at once), and returns its gas, status, logs, output and own-code gas
    """
    transaction_hash = anvil.rpc("eth_sendTransaction", transaction_request(transaction))
    receipt = anvil.wait_receipt(transaction_hash)
    trace = anvil.rpc("debug_traceTransaction", transaction_hash, {"tracer": "callTracer"})
    return {"gas_used": int(receipt["gasUsed"], 16), "status": int(receipt["status"], 16),
            "logs": normalized_logs(receipt), "output": trace.get("output", "0x"),
            "own_gas": own_code_gas(trace, address, intrinsic)}


# Errors of the free RPC plans (timeouts, rate limits) after which the whole transaction is replayed again
TRANSIENT_ERRORS = ("408", "429", "timeout", "Timeout", "Fork Error", "rate limit", "Rate limit", "not mined")


# EIP-7825 (Fusaka): maximum gas of a transaction
TRANSACTION_GAS_CAP = 2 ** 24


def deploy_variant(anvil: Anvil, deploy_info: Dict, creation_code: str, address: str) \
        -> Tuple[Optional[str], str, str]:
    """
    Executes the creation code + constructor arguments (eth_call) and returns the runtime code (None if the
    constructor fails), the deployer used and the error. The constructor runs from the creator (the factory, for
    contracts created by a contract) with the nonce it had at the creation, so msg.sender is the original one and a
    contract created with CREATE is created at its original address (immutables such as address(this) or EIP-712
    domain separators match; the code and nonce of the address are cleared first to avoid a collision). With CREATE2
    the address depends on the initcode, so it cannot match. Some constructors only accept the original
    transaction's sender (e.g. checks of tx.origin): if the constructor reverts from the factory, it is executed from
    that sender (without the nonce)
    """
    initcode = "0x" + creation_code + deploy_info["constructor_arguments"][2:]
    attempts = [(deploy_info["deployer"], deploy_info.get("creation_nonce"))]
    if deploy_info.get("factory") and deploy_info.get("creation_sender"):
        attempts.append((deploy_info["creation_sender"], None))
    error = ""
    for deployer, nonce in attempts:
        request = {"from": deployer, "gas": hex(TRANSACTION_GAS_CAP), "input": initcode}
        if nonce is not None:
            anvil.rpc("anvil_setCode", address, "0x")
            anvil.rpc("anvil_setNonce", address, "0x0")
            anvil.rpc("anvil_setNonce", deployer, nonce)
            request["nonce"] = nonce
        try:
            runtime_code = anvil.rpc("eth_call", request, "latest")
        except RuntimeError as exception:
            if "revert" not in str(exception):
                raise
            error = f"constructor reverted: {str(exception)[:200]}"
            continue
        if runtime_code in ("0x", None):
            error = "constructor returned no code"
            continue
        return runtime_code, deployer, ""
    return None, "", error


def replay_transaction(anvil: Anvil, replay_data: Dict, address: str, deploy_info: Dict,
                       codes_per_variant: Dict[str, Optional[str]], references_per_variant: Dict[str, Optional[Dict]],
                       measured_deployments: set, deployment_rows: List[Dict]) -> List[Dict]:
    """
    Rows of one transaction: the original replay and, if it reproduces the receipt, every variant's
    """
    transaction, receipt, block = replay_data["transaction"], replay_data["receipt"], replay_data["block"]
    block_number = int(block["number"], 16)
    base_row = {"address": address, "hash": transaction["hash"], "block": block_number,
                "selector": transaction["input"][:10]}
    # Same intrinsic gas for every variant: 21000 + calldata (+ access list, ignored in the subtraction)
    intrinsic = 21000 + intrinsic_calldata_gas(bytes.fromhex(transaction["input"][2:]), False)
    anvil.fork(block_number - 1, block)
    snapshot = anvil.snapshot()
    original = execute_transaction(anvil, transaction, address, intrinsic)
    valid = original["gas_used"] == int(receipt["gasUsed"], 16) and original["status"] == int(receipt["status"], 16)
    rows = [{**base_row, "variant": ORIGINAL, "gas_used": original["gas_used"], "own_gas": original["own_gas"],
             "status": original["status"], "receipt_gas_used": int(receipt["gasUsed"], 16), "valid": valid,
             "error": ""}]
    if not valid:
        return rows
    new_deployments = []
    for variant, creation_code in codes_per_variant.items():
        row = {**base_row, "variant": variant}
        if creation_code is None:
            rows.append({**row, "error": "no code"})
            continue
        snapshot = anvil.restart_from(snapshot, block)
        runtime_code, deployer, error = deploy_variant(anvil, deploy_info, creation_code, address)
        if runtime_code is None:
            rows.append({**row, "error": error})
            continue
        # The immutables computed by the constructor differ from the on-chain ones when they depend on the address
        # (CREATE2), on contracts created by the constructor or on the state: the on-chain values are written instead
        references, onchain_values = references_per_variant.get(variant), deploy_info.get("immutables") or {}
        immutables_changed, immutables_error = 0, ""
        if references:
            if onchain_values:
                patched, immutables_changed, immutables_error = patch_immutables(runtime_code, references,
                                                                                 onchain_values)
                runtime_code = patched or runtime_code
            else:
                immutables_error = "no on-chain values"
        elif references is None:
            immutables_error = "no immutable references"
        else:
            immutables_error = "no immutables"
        row.update(immutables_changed=immutables_changed, immutables_error=immutables_error)
        # Undo the changes of the deployment (code and nonces) before measuring and replaying
        snapshot = anvil.restart_from(snapshot, block)
        if variant not in measured_deployments:
            new_deployments.append(measure_deployment(anvil, deployer, creation_code, runtime_code, deploy_info,
                                                      address, variant, block_number))
            snapshot = anvil.restart_from(snapshot, block)
        anvil.rpc("anvil_setCode", address, runtime_code)
        result = execute_transaction(anvil, transaction, address, intrinsic)
        matches = result["status"] == original["status"] and result["logs"] == original["logs"] and \
            result["output"] == original["output"]
        rows.append({**row, "gas_used": result["gas_used"], "own_gas": result["own_gas"], "status": result["status"],
                     "matches_original": matches, "logs_match": result["logs"] == original["logs"],
                     "output_match": result["output"] == original["output"], "error": ""})
    # Only once the transaction is complete (a retried transaction must not measure them twice)
    for deployment in new_deployments:
        measured_deployments.add(deployment["variant"])
        deployment_rows.append(deployment)
    return rows


def replay_contract(address: str, data_dir: Path, codes_per_variant: Dict[str, Optional[str]], rpc_url: str,
                    anvil_binary: str, compute_units: int, reference_inputs: Dict, attempts: int = 4) \
        -> Tuple[List[Dict], List[Dict]]:
    """
    Rows per (transaction, variant) and per (contract, variant) deployment for one contract. A transaction that
    fails with a transient RPC error is replayed again from the fork (up to attempts times, with backoff).
    reference_inputs has what variant_immutable_references needs (artifacts folder, artifact name per variant,
    input, contract, solc, depth)
    """
    stored = read_json_gz(data_dir.joinpath("txs", f"{address}.json.gz"))
    deploy_info = read_json_gz(data_dir.joinpath("deploy", f"{address}.json.gz"))
    references_per_variant = {}
    for variant, creation_code in codes_per_variant.items():
        if creation_code is not None:
            references_per_variant[variant], _ = variant_immutable_references(
                reference_inputs["artifacts_dir"], reference_inputs["artifacts"][variant],
                reference_inputs["input_info"], reference_inputs["contract"], reference_inputs["solc"],
                reference_inputs["depth"])
    transaction_rows, deployment_rows, measured_deployments = [], [], set()
    anvil = Anvil(anvil_binary, rpc_url, compute_units)
    try:
        for replay_data in stored.get("replay_data") or []:
            transaction = replay_data["transaction"]
            base_row = {"address": address, "hash": transaction["hash"], "variant": ORIGINAL}
            if transaction.get("type") not in ("0x0", "0x1", "0x2"):
                transaction_rows.append({**base_row, "error": f"transaction type {transaction.get('type')}"})
                continue
            for attempt in range(attempts):
                requests_before = anvil.proxy.requests
                try:
                    rows = replay_transaction(anvil, replay_data, address, deploy_info, codes_per_variant,
                                              references_per_variant, measured_deployments, deployment_rows)
                    # Requests to the upstream RPC for the whole transaction (original and variants)
                    rows[0]["rpc_requests"] = anvil.proxy.requests - requests_before
                    transaction_rows.extend(rows)
                    break
                except Exception as exception:
                    message = f"{type(exception).__name__}: {str(exception)[:300]}"
                    if attempt == attempts - 1 or not any(pattern in message for pattern in TRANSIENT_ERRORS):
                        transaction_rows.append({**base_row, "error": message})
                        break
                    time.sleep(30 * (attempt + 1))
    finally:
        anvil.close()
    return transaction_rows, deployment_rows


def measure_deployment(anvil: Anvil, deployer: str, creation_code: str, runtime_code: str, deploy_info: Dict,
                       address: str, variant: str, block_number: int) -> Dict:
    """
    Mines the deployment from the deployer (impersonated, funded) at a fresh address (its current nonce, so the
    storage of the original contract does not change the cost of the constructor's stores) and returns its gas,
    with the deposit (200 per runtime byte) and the intrinsic calldata part apart, and the number of Sourcify's
    immutable values missing in the runtime code obtained at the original address
    """
    initcode = "0x" + creation_code + deploy_info["constructor_arguments"][2:]
    anvil.rpc("anvil_setBalance", deployer, hex(10 ** 24))
    transaction_hash = anvil.rpc("eth_sendTransaction", {"from": deployer, "gas": hex(TRANSACTION_GAS_CAP),
                                                         "input": initcode})
    receipt = anvil.wait_receipt(transaction_hash)
    runtime_bytes = (len(runtime_code) - 2) // 2
    immutables = [value[2:].lower() for value in deploy_info.get("immutables", {}).values()]
    missing_immutables = sum(1 for value in immutables if value.strip("0") and value not in runtime_code.lower())
    return {"address": address, "variant": variant, "block": block_number, "deployer": deployer,
            "deployer_is_creator": deployer == deploy_info["deployer"],
            "gas_used": int(receipt["gasUsed"], 16), "status": int(receipt["status"], 16),
            "runtime_bytes": runtime_bytes, "deposit_gas": 200 * runtime_bytes,
            "initcode_bytes": (len(initcode) - 2) // 2,
            "calldata_gas": intrinsic_calldata_gas(bytes.fromhex(initcode[2:]), True),
            "immutables": len(immutables), "missing_immutables": missing_immutables}


def replay(args) -> None:
    sources = {ADDRESS_PATTERN.search(line).group(0).lower(): Path(line.strip())
               for line in args.inputs_from.read_text().splitlines() if ADDRESS_PATTERN.search(line)}
    addresses = [address for address in sorted(sources)
                 if args.data_dir.joinpath("txs", f"{address}.json.gz").is_file()
                 and args.data_dir.joinpath("deploy", f"{address}.json.gz").is_file()]
    addresses = addresses[:args.limit] if args.limit else addresses
    jobs = args.jobs or jobs_from_load()
    compute_units = max(1, args.compute_units // jobs)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    print(f"{len(addresses)} contracts with data, {jobs} jobs, {compute_units} compute units/s per anvil", flush=True)
    artifacts_dir = args.results_dir.joinpath("artifacts")

    def contract_name(address: str) -> Optional[str]:
        contract = read_json_gz(args.data_dir.joinpath("deploy", f"{address}.json.gz")).get("contract")
        etherscan_file = ETHERSCAN_FOLDER.joinpath(f"{address}.json")
        if etherscan_file.is_file():
            contract = json.loads(etherscan_file.read_text()).get("ContractName") or contract
        return contract

    def reference_inputs(address: str) -> Dict:
        return {"artifacts_dir": artifacts_dir, "artifacts": dict(args.variants), "contract": contract_name(address),
                "input_info": input_info_for(sources[address], args.solc), "solc": args.solc.resolve(),
                "depth": args.depth}

    def codes_for(address: str) -> Dict[str, Optional[str]]:
        contract = contract_name(address)
        codes = {}
        for name, artifact_name in args.variants:
            variant_codes = variant_creation_codes(artifacts_dir, artifact_name,
                                                   input_info_for(sources[address], args.solc), args.depth)
            code = None if variant_codes is None else variant_codes.get(contract)
            codes[name] = None if code is None or "__$" in code else code
        return codes

    transaction_rows, deployment_rows = [], []
    with ProcessPoolExecutor(max_workers=jobs) as executor:
        futures = {address: executor.submit(replay_contract, address, args.data_dir, codes_for(address), args.rpc,
                                            args.anvil, compute_units, reference_inputs(address))
                   for address in addresses}
        for index, (address, future) in enumerate(futures.items(), 1):
            try:
                rows, deployments = future.result()
            except Exception as exception:
                rows, deployments = [{"address": address, "variant": ORIGINAL,
                                      "error": f"{type(exception).__name__}: {exception}"}], []
            transaction_rows.extend(rows)
            deployment_rows.extend(deployments)
            if index % 20 == 0:
                print(f"{index} / {len(addresses)}", flush=True)
                pd.DataFrame(transaction_rows).to_csv(args.out_dir.joinpath("transactions.csv.gz"), index=False)
                try:
                    ensure_free_space(args.out_dir, args.min_free_gb)
                except NotEnoughDiskSpace as exception:
                    print(f"Stopping: {exception}", flush=True)
                    for pending in futures.values():
                        pending.cancel()
                    break
    pd.DataFrame(transaction_rows).to_csv(args.out_dir.joinpath("transactions.csv.gz"), index=False)
    pd.DataFrame(deployment_rows).to_csv(args.out_dir.joinpath("deployments.csv.gz"), index=False)
    args.out_dir.joinpath("variants.json").write_text(json.dumps([name for name, _ in args.variants]))
    report(argparse.Namespace(out_dir=args.out_dir))


# ---------------------------------------------------------------- report

TRANSACTION_COLUMNS = ["address", "hash", "block", "selector", "variant", "gas_used", "own_gas", "status",
                       "receipt_gas_used", "valid", "matches_original", "logs_match", "output_match",
                       "immutables_changed", "immutables_error", "rpc_requests", "error"]


def read_csv_or_empty(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path)
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return pd.DataFrame()


def report(args) -> None:
    transactions = read_csv_or_empty(args.out_dir.joinpath("transactions.csv.gz")).reindex(
        columns=TRANSACTION_COLUMNS)
    transactions["error"] = transactions["error"].fillna("")
    deployments = read_csv_or_empty(args.out_dir.joinpath("deployments.csv.gz"))
    variants = json.loads(args.out_dir.joinpath("variants.json").read_text())
    reference = variants[0]
    originals = transactions[transactions.variant == ORIGINAL]
    lines = [f"Mainnet replay: {originals.address.nunique()} contracts, {originals.hash.nunique()} transactions",
             f"  original replay errors: {(originals.error != '').sum()}, "
             f"matching the receipt: {int(originals.valid.fillna(False).sum())} / {(originals.error == '').sum()}"]
    if originals.rpc_requests.notna().any():
        lines.append(f"  RPC requests per replayed transaction (original + variants): mean "
                     f"{originals.rpc_requests.mean():.0f}, max {originals.rpc_requests.max():.0f}, total "
                     f"{originals.rpc_requests.sum():.0f}")
    measured = transactions[(transactions.variant != ORIGINAL)]
    complete = measured[measured.error == ""].groupby("hash").variant.nunique()
    complete_hashes = set(complete[complete == len(variants)].index)
    matching = measured[measured.hash.isin(complete_hashes)].groupby("hash").matches_original.all()
    validated = set(matching[matching].index)
    lines.append(f"  measured by every variant: {len(complete_hashes)}, all matching the original: {len(validated)}")
    if "immutables_error" in measured and measured.immutables_error.notna().any():
        patched = measured[(measured.error == "") & measured.immutables_error.isna()]
        lines.append(f"  immutables: replays with the on-chain values written {len(patched)}, of which with values "
                     f"changed {int((patched.immutables_changed > 0).sum())}; not written: "
                     f"{dict(measured[measured.immutables_error.notna()].immutables_error.str[:60].value_counts())}")
    for variant in variants:
        mismatches = measured[(measured.variant == variant) & (measured.error == "") & ~measured.matches_original.fillna(True).astype(bool)]
        errors = measured[(measured.variant == variant) & (measured.error != "")]
        lines.append(f"  {variant}: {len(mismatches)} mismatches with the original, errors: "
                     f"{dict(errors.error.value_counts())}")
        for _, row in mismatches.head(20).iterrows():
            lines.append(f"    mismatch {row.address} {row.hash} (logs {row.logs_match}, output {row.output_match})")
    pivot = measured[measured.hash.isin(validated)].pivot_table(index=["address", "hash"], columns="variant",
                                                               values=["gas_used", "own_gas"], aggfunc="first")
    for variant in variants[1:] if len(validated) > 0 else []:
        lines.append(f"\n{variant} vs {reference} over {len(pivot)} validated transactions "
                     f"({pivot.index.get_level_values('address').nunique()} contracts):")
        for measure in ["gas_used", "own_gas"]:
            values = pivot[measure]
            reference_total, variant_total = int(values[reference].sum()), int(values[variant].sum())
            difference = variant_total - reference_total
            per_tx = values[variant] - values[reference]
            lines.append(f"  {measure:<9} {reference}: {reference_total:>14,}  {variant}: {variant_total:>14,}  diff "
                         f"{difference:>+12,} ({100 * difference / reference_total:+.3f}%)  better / worse / equal "
                         f"{(per_tx < 0).sum()} / {(per_tx > 0).sum()} / {(per_tx == 0).sum()}")
        per_contract = (pivot["own_gas"][variant] - pivot["own_gas"][reference]).groupby("address").sum()
        lines.append(f"  contracts with more own gas: {(per_contract > 0).sum()}, less: {(per_contract < 0).sum()}, "
                     f"equal: {(per_contract == 0).sum()}; largest regressions:")
        for contract_address, difference in per_contract.sort_values(ascending=False).head(10).items():
            if difference > 0:
                lines.append(f"    {difference:>+9,}  {contract_address}")
        if len(deployments) > 0:
            deployed = deployments[deployments.status == 1].pivot_table(
                index="address", columns="variant", values=["gas_used", "deposit_gas", "calldata_gas"], aggfunc="first")
            deployed = deployed.dropna()
            for measure in ["gas_used", "deposit_gas", "calldata_gas"]:
                reference_total, variant_total = int(deployed[measure][reference].sum()), int(deployed[measure][variant].sum())
                lines.append(f"  deployment {measure:<13} ({len(deployed)} contracts) {reference}: {reference_total:>13,}  "
                             f"{variant}: {variant_total:>13,}  diff {variant_total - reference_total:>+11,} "
                             f"({100 * (variant_total - reference_total) / max(1, reference_total):+.3f}%)")
            missing = deployments[deployments.missing_immutables > 0]
            lines.append(f"  deployments with immutables different from Sourcify's: {len(missing)} of {len(deployments)} "
                         f"(not every immutable survives in the code: compare with the original address)")
            if "deployer_is_creator" in deployments:
                lines.append(f"  constructors executed from the original creator: "
                             f"{int(deployments.deployer_is_creator.fillna(False).astype(bool).sum())} of "
                             f"{len(deployments)} (the rest from the creation transaction's sender)")
    summary = "\n".join(lines)
    args.out_dir.joinpath("summary.txt").write_text(summary + "\n")
    print(summary)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="stage", required=True)

    etherscan_parser = subparsers.add_parser("fetch-etherscan")
    etherscan_parser.add_argument("addresses", type=Path, help="File with the addresses (or paths that contain them)")
    etherscan_parser.add_argument("--etherscan-dir", type=Path, dest="etherscan_dir", default=ETHERSCAN_FOLDER)

    fetch_txs_parser = subparsers.add_parser("fetch-txs")
    fetch_txs_parser.add_argument("addresses", type=Path)
    fetch_txs_parser.add_argument("data_dir", type=Path)
    fetch_txs_parser.add_argument("--end-block", type=int, dest="end_block", default=None,
                                  help="Last block of the window (fixed, for reproducibility)")
    fetch_txs_parser.add_argument("--window", type=int, default=50_000, help="Blocks (~1 week)")
    fetch_txs_parser.add_argument("--per-contract", type=int, dest="per_contract", default=5)
    fetch_txs_parser.add_argument("--rpc", default="https://eth.drpc.org")
    fetch_txs_parser.add_argument("--rpc-file", type=Path, dest="rpc_file", default=None,
                         help="File with the RPC URL (e.g. one with an API key), instead of --rpc")
    fetch_txs_parser.add_argument("--from-cache", action="store_true", dest="from_cache",
                                  help="Only complete stored selections (e.g. from load-bigquery) with RPC data")
    fetch_txs_parser.add_argument("--missing-from", type=Path, nargs="+", dest="missing_from", default=None,
                                  help="BigQuery export: only the contracts without transactions in it, sampled "
                                       "--per-selector going back from --end-block (not before Shanghai)")
    fetch_txs_parser.add_argument("--per-selector", type=int, dest="per_selector", default=20)

    sample_parser = subparsers.add_parser("sample-size")
    sample_parser.add_argument("addresses", type=Path, help="The list of contracts (e.g. inputs_most_called.txt)")
    sample_parser.add_argument("export_files", type=Path, nargs="+", help="Export of sample_txs.sql (NDJSON[.gz])")
    sample_parser.add_argument("--per-bucket", type=int, dest="per_bucket", default=20)
    sample_parser.add_argument("--min-raw-transactions", type=int, dest="min_raw_transactions", default=20,
                          help="Contracts without ABI functions: raw selectors with fewer transactions go to 'other'")

    import_parser = subparsers.add_parser("import-bigquery-json")
    import_parser.add_argument("bq_json", type=Path, help="Output of bq --format=json head -n N <table>")
    import_parser.add_argument("output", type=Path, help="NDJSON .gz to write")
    import_parser.add_argument("--expected-rows", type=int, dest="expected_rows", default=None,
                               help="Number of rows of the table (numRows of bq show): fails if fewer were read")

    query_parser = subparsers.add_parser("make-bigquery-query")
    query_parser.add_argument("addresses", type=Path)
    query_parser.add_argument("--template", type=Path, default=Path(__file__).parent.joinpath(
        "gas", "bigquery", "sample_txs.sql"))
    query_parser.add_argument("--output", type=Path, default=Path(__file__).parent.joinpath(
        "gas", "bigquery", "sample_txs.sql"))

    deploy_parser = subparsers.add_parser("fetch-deploy")
    deploy_parser.add_argument("addresses", type=Path)
    deploy_parser.add_argument("data_dir", type=Path)
    deploy_parser.add_argument("--rpc", default="https://eth.drpc.org")
    deploy_parser.add_argument("--rpc-file", type=Path, dest="rpc_file", default=None,
                         help="File with the RPC URL (e.g. one with an API key), instead of --rpc")

    bigquery_parser = subparsers.add_parser("load-bigquery")
    bigquery_parser.add_argument("export_files", type=Path, nargs="+")
    bigquery_parser.add_argument("data_dir", type=Path)
    bigquery_parser.add_argument("--per-bucket", type=int, dest="per_bucket", default=20)
    bigquery_parser.add_argument("--min-raw-transactions", type=int, dest="min_raw_transactions", default=20,
                          help="Contracts without ABI functions: raw selectors with fewer transactions go to 'other'")

    prestate_parser = subparsers.add_parser("fetch-prestate")
    prestate_parser.add_argument("data_dir", type=Path)
    prestate_parser.add_argument("--rpc", default="https://eth.drpc.org")
    prestate_parser.add_argument("--rpc-file", type=Path, dest="rpc_file", default=None,
                                 help="File with the RPC URL (e.g. one with an API key), instead of --rpc")
    prestate_parser.add_argument("--requests-per-second", type=float, dest="requests_per_second", default=40,
                                 help="Total rate of requests to the RPC, shared by the jobs")
    prestate_parser.add_argument("--jobs", type=int, default=None)
    prestate_parser.add_argument("--limit", type=int, default=None, help="Only the first N contracts (pilot)")
    prestate_parser.add_argument("--min-free-gb", type=float, dest="min_free_gb", default=50)

    replay_parser = subparsers.add_parser("replay")
    replay_parser.add_argument("data_dir", type=Path)
    replay_parser.add_argument("results_dir", type=Path, help="Output folder of compare_variants.py --keep-artifacts")
    replay_parser.add_argument("--inputs-from", type=Path, dest="inputs_from", required=True)
    replay_parser.add_argument("--solc", type=Path, required=True)
    replay_parser.add_argument("--variant", dest="variants", action="append", required=True,
                               type=lambda value: tuple(value.split("=", 1)),
                               help="NAME=ARTIFACT_FOLDER; the first one is the reference")
    replay_parser.add_argument("--rpc", default="https://eth.drpc.org")
    replay_parser.add_argument("--rpc-file", type=Path, dest="rpc_file", default=None,
                         help="File with the RPC URL (e.g. one with an API key), instead of --rpc")
    replay_parser.add_argument("--anvil", default=str(Path.home().joinpath(".foundry", "bin", "anvil")))
    replay_parser.add_argument("--compute-units", type=int, dest="compute_units", default=300,
                               help="Total RPC compute units per second, shared by the anvil processes")
    replay_parser.add_argument("--out-dir", type=Path, dest="out_dir", required=True)
    replay_parser.add_argument("--depth", type=int, default=16)
    replay_parser.add_argument("--jobs", type=int, default=None)
    replay_parser.add_argument("--limit", type=int, default=None)
    replay_parser.add_argument("--min-free-gb", type=float, dest="min_free_gb", default=50)

    report_parser = subparsers.add_parser("report")
    report_parser.add_argument("out_dir", type=Path)

    args = parser.parse_args()
    if getattr(args, "rpc_file", None) is not None:
        args.rpc = args.rpc_file.read_text().strip()
    if args.stage == "fetch-etherscan":
        fetch_etherscan(args)
    elif args.stage == "fetch-txs":
        if args.end_block is None and not args.from_cache:
            sys.exit("--end-block is required (fix it once and record it, for reproducibility)")
        fetch_txs(args)
    elif args.stage == "sample-size":
        sample_size(args)
    elif args.stage == "import-bigquery-json":
        import_bigquery_json(args)
    elif args.stage == "make-bigquery-query":
        make_bigquery_query(args)
    elif args.stage == "fetch-deploy":
        fetch_deploy(args)
    elif args.stage == "load-bigquery":
        load_bigquery(args)
    elif args.stage == "fetch-prestate":
        fetch_prestate(args)
    elif args.stage == "replay":
        replay(args)
    else:
        report(args)


if __name__ == "__main__":
    main()
