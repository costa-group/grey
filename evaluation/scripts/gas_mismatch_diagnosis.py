#!/usr/bin/env python3
"""
Diagnosis of the transactions in which a variant does not match the original in the offline replay
(gas_offline_replay.py replay): is the difference legitimate (the program observes the gas or its own code, which
any recompilation changes), or a bug of the variant?

Per mismatching transaction (receipt valid), the original, solc and grey are executed again exactly as in the replay
(same t8n, uniform fork, block gas limit), with execution traces, and:
  - diffs: the logs (word by word: topics and 32-byte words of the data) and the state (storage slots, nonces, codes)
    of each variant against the original, and of grey against solc;
  - gas: a differing word is explained by the gas if its change is proportional to the change of the gas used by the
    transaction: (v_variant - v_original) = k (gas_variant - gas_original) with the same k for solc and grey (when
    both differ) or k in {±1, ±gas price, ±base fee} (refunds, gasUsed counters, fees);
  - code: a differing word is explained by the code if the original value is the size (or hash) of the original code
    at the replaced address and the variant's value is the size (or hash) of the variant's code. A transaction is
    code-dependent as a whole when the replaced code creates contracts, or predicts CREATE2 addresses (KECCAK256 over
    85 bytes), from initcode embedded in it: the created code and the addresses change with any recompilation;
  - perturbation: the original is executed again with an EIP-2930 access list of every account and slot it reads,
    which changes its gas consumption (cold vs warm accesses) but not its semantics. A word that changes there depends
    on the gas consumed, as a recompilation changes it too;
  - probes in the traces: the gas observations (GAS, and calls that forward all the remaining gas, whose callee gets
    63/64 of it) and the code observations (CODESIZE/CODECOPY, EXTCODESIZE/EXTCODEHASH/EXTCODECOPY of the replaced
    address, CREATE2) made by the replaced code; and whether the original's own outcome changes with the gas limit
    of the transaction (its own limit vs the block's), which shows that the program depends on the gas available.
Classes per transaction and variant:
  - gas / code / gas+code: every differing word is explained;
  - same as solc: grey's logs and state equal solc's (the difference comes from recompiling, not from grey);
  - status: the status differs (reported with the probes; not explained automatically);
  - UNEXPLAINED: to be investigated.

Usage (on grey-remote, from ~/grey_eval, after a replay):
    python3 evaluation/scripts/gas_mismatch_diagnosis.py gas/ranking_2021_2026 results/<replay_out> \\
        --variants-dir results/<compilation>/codes_immutables --t8n gas/build/evmone-0.24.0/evmone \\
        --out-dir results/<replay_out>/diagnosis [--per-contract N] [--jobs N]
Writes <out>/transactions.csv (one row per transaction and variant), <out>/summary.txt (per contract), and
<out>/accounting.csv / accounting.txt: the category of every sampled transaction (compared, a variant without code,
gas- or code-dependent mismatch, exclusion, receipt not reproduced).
"""

import argparse
import json
import shutil
import subprocess
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

try:
    from Crypto.Hash import keccak
except ImportError:
    # Without pycryptodome (grey-remote) the code hashes are not checked, only the code sizes
    keccak = None

from gas_common import jobs_from_load
from gas_mainnet_replay import read_json_gz
from gas_offline_replay import (CodeStore, alloc_from_prestate, comparable_state, environment, raised_gas_limit,
                                signed_transaction)

CALL_OPS = {"CALL", "CALLCODE", "DELEGATECALL", "STATICCALL"}
CODE_OPS_OWN = {"CODESIZE", "CODECOPY"}
CODE_OPS_EXTERNAL = {"EXTCODESIZE", "EXTCODEHASH", "EXTCODECOPY"}


def keccak_hex(code_hex: str) -> Optional[int]:
    if keccak is None:
        return None
    digest = keccak.new(digest_bits=256)
    digest.update(bytes.fromhex(code_hex.removeprefix("0x")))
    return int(digest.hexdigest(), 16)


def trace_probes(trace_file: Path, entry_address: str, code_address: str) -> Dict[str, int]:
    """
    Gas and code observations made while the replaced code runs (frames whose code is at code_address), from an
    EIP-3155 trace. The code address of each frame is followed through the calls: the target of CALL, CALLCODE,
    DELEGATECALL and STATICCALL is the second stack item (CREATE frames are marked unknown)
    """
    probes = {"gas_ops": 0, "all_gas_calls": 0, "own_code_ops": 0, "external_code_ops": 0, "create2": 0,
              "gas_readings": [], "create2_predictions": []}
    previous_gas_op = previous_prediction = False
    frames: List[Optional[str]] = [entry_address]
    pending: Optional[str] = None
    for line in trace_file.read_text().splitlines():
        if not line.startswith('{"pc"'):
            continue
        step = json.loads(line)
        depth, op, stack = step["depth"], step.get("opName", ""), step.get("stack", [])
        # The value pushed by a GAS (or a KECCAK256) is on top of the stack at the next step
        if previous_gas_op and stack:
            probes["gas_readings"].append(int(stack[-1], 16))
        if previous_prediction and stack:
            probes["create2_predictions"].append(int(stack[-1], 16) % 2 ** 160)
        previous_gas_op = previous_prediction = False
        # Entering a deeper frame: the code address noted at the call (None for creates)
        while len(frames) < depth:
            frames.append(pending)
            pending = None
        del frames[depth:]
        in_replaced = frames[depth - 1] == code_address
        if op in CALL_OPS and len(stack) >= 2:
            pending = "0x" + stack[-2].removeprefix("0x").rjust(40, "0")[-40:]
            if in_replaced and int(stack[-1], 16) >= int(step["gas"], 16) - int(step.get("gasCost", "0x0"), 16):
                probes["all_gas_calls"] += 1
        elif op in ("CREATE", "CREATE2"):
            pending = None
            probes["create2"] += op == "CREATE2" and in_replaced
        if not in_replaced:
            continue
        if op == "GAS":
            probes["gas_ops"] += 1
            previous_gas_op = True
        elif op == "KECCAK256" and len(stack) >= 2 and int(stack[-2], 16) == 0x55:
            # The CREATE2 address formula keccak256(0xff ++ deployer ++ salt ++ keccak256(initcode)): an address
            # predicted from an initcode embedded in the code (e.g. OpenZeppelin's Create2.computeAddress)
            previous_prediction = True
        elif op in CODE_OPS_OWN:
            probes["own_code_ops"] += 1
        elif op in CODE_OPS_EXTERNAL and stack and \
                "0x" + stack[-1].removeprefix("0x").rjust(40, "0")[-40:] == code_address:
            probes["external_code_ops"] += 1
    return probes


def execute(t8n: str, alloc: Dict, env: Dict, transaction: Dict, fork: str, folder: Path, trace: bool) -> Dict:
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    for name, content in [("alloc.json", alloc), ("env.json", env), ("txs.json", [transaction])]:
        folder.joinpath(name).write_text(json.dumps(content))
    command = [t8n, "t8n", "--input.alloc", "alloc.json", "--input.env", "env.json", "--input.txs", "txs.json",
               "--output.basedir", ".", "--output.result", "result.json", "--output.alloc", "post.json",
               "--state.fork", fork, "--state.chainid", "1", "--state.reward", "0"] + (["--trace"] if trace else [])
    completed = subprocess.run(command, capture_output=True, text=True, cwd=folder, timeout=600)
    result_file = folder.joinpath("result.json")
    if completed.returncode != 0 or not result_file.is_file():
        return {"error": (completed.stderr or completed.stdout)[-200:]}
    result = json.loads(result_file.read_text())
    if result.get("rejected"):
        return {"error": str(result["rejected"][0].get("error"))[:200]}
    receipt = result["receipts"][0]
    traces = sorted(folder.glob("trace-*.jsonl"))
    return {"status": int(receipt["status"], 16), "gas_used": int(receipt["gasUsed"], 16),
            "logs": [(log["address"].lower(), list(log["topics"]), log["data"]) for log in receipt.get("logs") or []],
            "post": json.loads(folder.joinpath("post.json").read_text()), "trace": traces[0] if traces else None,
            "error": ""}


def with_warm_access_list(transaction: Dict, prestate: Dict) -> Dict:
    """
    The same transaction with an EIP-2930 access list of every account and storage slot of its prestate (what it
    reads): the semantics do not change, but the gas consumed (and every gasleft() reading) does. A legacy
    transaction becomes type 1 with the same gas price (evmone does not check the signature)
    """
    perturbed = {key: value for key, value in transaction.items() if key != "hash"}
    if int(perturbed.get("type", "0x0"), 16) == 0:
        perturbed["type"], perturbed["chainId"] = "0x1", "0x1"
    perturbed["accessList"] = [{"address": address, "storageKeys": sorted((account.get("storage") or {}).keys())}
                               for address, account in sorted(prestate.items())]
    return perturbed


def created_accounts(prestate: Dict, post: Dict) -> set:
    """
    Accounts with code in the post state that had no code in the prestate (created by the transaction), as
    lower-case 0x-prefixed 40-digit addresses
    """
    before = {address.lower() for address, account in prestate.items() if account.get("code") not in (None, "0x")}
    return {"0x" + format(int(address, 16), "040x") for address, account in post.items()
            if account.get("code") not in (None, "0x") and address.lower() not in before}


def word_kind(where: str) -> str:
    """
    The kind of a differing word, without the concrete storage slot (which changes with the users of each
    transaction): <account>.balance, <account>[slot] or log<i>[<word>]
    """
    return where.split("[")[0] + "[slot]" if where.startswith("0x") and "[" in where else where


def family(kind: str) -> str:
    """
    A word kind with the log index removed (log<i>[<word>] -> log[<word>]): which logs carry a gas-dependent value can
    change with the gas
    """
    return "log[" + kind.split("[", 1)[1] if kind.startswith("log") else kind


def log_words(log: Tuple) -> List[int]:
    address, topics, data = log
    data = data.removeprefix("0x")
    return [int(topic, 16) for topic in topics] + [int(data[i:i + 64].ljust(64, "0"), 16)
                                                    for i in range(0, len(data), 64)]


def differing_words(original: Dict, variant: Dict, code_address: str, ignored: set) -> Tuple[List[Tuple], List[str]]:
    """
    (where, original value, variant value) of every differing word of the logs and of the storage, and the
    differences whose shape cannot be compared word by word (another number of logs or of words, nonces, codes)
    """
    words, structural = [], []
    if len(original["logs"]) != len(variant["logs"]):
        structural.append(f"logs {len(original['logs'])} -> {len(variant['logs'])}")
    for index, (log_o, log_v) in enumerate(zip(original["logs"], variant["logs"])):
        words_o, words_v = log_words(log_o), log_words(log_v)
        if log_o[0] != log_v[0] or len(words_o) != len(words_v):
            structural.append(f"log{index} emitter or size")
            continue
        words += [(f"log{index}[{i}]", a, b) for i, (a, b) in enumerate(zip(words_o, words_v)) if a != b]
    state_o = comparable_state(original["post"], code_address, ignored)
    state_v = comparable_state(variant["post"], code_address, ignored)
    for account in sorted(set(state_o) | set(state_v)):
        entry_o, entry_v = state_o.get(account, {}), state_v.get(account, {})
        for field in ("nonce", "code", "balance"):
            if entry_o.get(field) != entry_v.get(field):
                if field == "balance":
                    words.append((f"{account}.balance", int(entry_o.get(field) or "0x0", 16),
                                  int(entry_v.get(field) or "0x0", 16)))
                else:
                    structural.append(f"{account}.{field}")
        storage_o, storage_v = entry_o.get("storage", {}), entry_v.get("storage", {})
        for slot in sorted(set(storage_o) | set(storage_v)):
            if storage_o.get(slot) != storage_v.get(slot):
                words.append((f"{account}[{slot}]", int(storage_o.get(slot, "0x0"), 16),
                              int(storage_v.get(slot, "0x0"), 16)))
    return words, structural


def diagnose_transaction(address: str, transaction_hash: str, data_dir: Path, variants_dir: Path,
                         variants: List[str], t8n: str, fork: str) -> List[Dict]:
    codes = CodeStore(data_dir.joinpath("codes"))
    deploy_file = data_dir.joinpath("deploy", f"{address}.json.gz")
    deploy_info = read_json_gz(deploy_file) if deploy_file.is_file() else {}
    code_address = deploy_info.get("code_address") or address
    data = next(entry for entry in read_json_gz(data_dir.joinpath("txs", f"{address}.json.gz"))["prestate_data"]
                if entry["transaction"]["hash"] == transaction_hash)
    transaction, block = signed_transaction(data["transaction"]), data["block"]
    raised, raised_prestate = raised_gas_limit(transaction, block, data["prestate"])
    # The replay's environment: a blob transaction rejected for its blob fee is replayed with a neutral one
    env = environment(block, fork, data.get("block_hashes"))
    if int(transaction.get("type", "0x0"), 16) == 3:
        with tempfile.TemporaryDirectory(prefix="gas_blob_") as probe:
            if "BLOB_GAS" in execute(t8n, alloc_from_prestate(raised_prestate, codes, None), env, raised, fork,
                                     Path(probe, "run"), False).get("error", ""):
                env = environment(block, fork, data.get("block_hashes"), True)
    original_code = next((codes.get(account["code"]) for key, account in data["prestate"].items()
                          if key.lower() == code_address and account.get("code")), "0x")
    variant_codes = {variant: read_json_gz(variants_dir.joinpath(variant, f"{address}.json.gz"))["runtime"]
                     for variant in variants}
    gas_price = int(transaction.get("gasPrice") or transaction.get("maxFeePerGas") or "0x0", 16)
    base_fee = int(block.get("baseFeePerGas") or "0x0", 16)
    ignored = {transaction["from"].lower(), block["miner"].lower()}
    rows = []
    with tempfile.TemporaryDirectory(prefix="gas_diagnosis_") as work:
        outcomes = {"original": execute(t8n, alloc_from_prestate(raised_prestate, codes, None), env, raised, fork,
                                        Path(work, "original"), True)}
        for variant in variants:
            outcomes[variant] = execute(t8n, alloc_from_prestate(raised_prestate, codes,
                                                                 (code_address, variant_codes[variant])),
                                        env, raised, fork, Path(work, variant), True)
        # Probe: the original with the transaction's own gas limit (the sender's balance is the original one)
        own_limit = execute(t8n, alloc_from_prestate(data["prestate"], codes, None), env, transaction, fork,
                            Path(work, "own_limit"), False)
        original = outcomes["original"]
        if original["error"]:
            return [{"address": address, "hash": transaction_hash, "variant": "original", "class": "error",
                     "detail": original["error"]}]
        own_limit_words = {}
        if not own_limit["error"]:
            # The values that the original takes with less gas available (its own limit): a variant that takes the
            # same values differs because of the gas available, not of its code
            own_limit_words = {where: value for where, _, value in
                               differing_words(original, own_limit, code_address, ignored)[0]}
        limit_sensitive = bool(not own_limit["error"] and (
            own_limit["status"] != original["status"] or own_limit["logs"] != original["logs"] or
            comparable_state(own_limit["post"], code_address, ignored) !=
            comparable_state(original["post"], code_address, ignored)))
        # Probe: the original with every read account and slot pre-warmed (only the gas consumption changes)
        warm = execute(t8n, alloc_from_prestate(raised_prestate, codes, None), env,
                       with_warm_access_list(raised, data["prestate"]), fork, Path(work, "warm"), False)
        gas_dependent_words, warm_status_changes = set(), False
        if not warm["error"]:
            warm_status_changes = warm["status"] != original["status"]
            warm_words, warm_structural = differing_words(original, warm, code_address, ignored)
            gas_dependent_words = {where for where, _, _ in warm_words} | set(warm_structural)
        original_probes = trace_probes(original["trace"], data["transaction"]["to"].lower(), code_address) \
            if original["trace"] else {}
        words_per_variant = {}
        for variant in variants:
            outcome = outcomes[variant]
            if outcome["error"]:
                rows.append({"address": address, "hash": transaction_hash, "variant": variant, "class": "error",
                             "detail": outcome["error"]})
                continue
            words, structural = differing_words(original, outcome, code_address, ignored)
            words_per_variant[variant] = (words, structural)
        # Grey vs solc, to separate the effects of recompiling from grey's
        same_as_solc = None
        if {"solc", "grey"} <= set(words_per_variant):
            solc, grey = outcomes["solc"], outcomes["grey"]
            same_as_solc = solc["status"] == grey["status"] and solc["logs"] == grey["logs"] and \
                comparable_state(solc["post"], code_address, ignored) == \
                comparable_state(grey["post"], code_address, ignored)
        for variant, (words, structural) in words_per_variant.items():
            outcome = outcomes[variant]
            if outcome["status"] == original["status"] and not words and not structural:
                continue
            gas_delta = outcome["gas_used"] - original["gas_used"]
            variant_code = variant_codes[variant].removeprefix("0x")
            sizes = (len(original_code.removeprefix("0x")) // 2, len(variant_code) // 2)
            hashes = (keccak_hex(original_code), keccak_hex(variant_code))
            probes = trace_probes(outcome["trace"], data["transaction"]["to"].lower(), code_address) \
                if outcome["trace"] else {}
            readings_o = original_probes.get("gas_readings", [])
            readings_v = probes.get("gas_readings", [])
            # Gas differences observable by the program: a reading, or a span between two readings (gasleft()
            # before - gasleft() after), compared between the variant and the original (aligned by occurrence)
            common = min(len(readings_o), len(readings_v))
            gas_deltas = {readings_v[i] - readings_o[i] for i in range(common)} | \
                {(readings_v[i] - readings_v[j]) - (readings_o[i] - readings_o[j])
                 for i in range(common) for j in range(i + 1, min(common, i + 64))}
            gas_deltas.add(gas_delta)
            gas_deltas.discard(0)
            factors = {1, gas_price, base_fee} - {0}
            created_o, created_v = created_accounts(data["prestate"], original["post"]), \
                created_accounts(data["prestate"], outcome["post"])
            explained_gas, explained_code, unexplained = [], [], []
            for where, value_o, value_v in words:
                delta = value_v - value_o
                # Values that wrap (e.g. gasleft() differences stored as two's complement) are taken signed
                if delta > 2 ** 255:
                    delta -= 2 ** 256
                elif delta < -2 ** 255:
                    delta += 2 ** 256
                other = [v for v in words_per_variant if v != variant]
                consistent = any(delta == sign * factor * observed for observed in gas_deltas for factor in factors
                                 for sign in (1, -1))
                if gas_delta != 0 and delta % gas_delta == 0:
                    k = delta // gas_delta
                    consistent = abs(k) in factors
                    # The same factor for the other variant (affine in the gas used)
                    for other_variant in other:
                        other_words = {w: (a, b) for w, a, b in words_per_variant[other_variant][0]}
                        other_delta_gas = outcomes[other_variant]["gas_used"] - original["gas_used"]
                        if where in other_words and other_delta_gas != 0:
                            other_delta = other_words[where][1] - other_words[where][0]
                            consistent = consistent or other_delta * gas_delta == delta * other_delta_gas
                if consistent or where in gas_dependent_words or own_limit_words.get(where) == value_v:
                    explained_gas.append(where)
                elif (value_o, value_v) in (sizes, hashes) or \
                        ("0x" + format(value_o, "040x") in created_o and "0x" + format(value_v, "040x") in created_v) or \
                        any(account in where for account in created_o | created_v):
                    # The size/hash of the code, an address created with CREATE2 (it depends on the initcode), or a
                    # value of such an account
                    explained_code.append(where)
                else:
                    unexplained.append(f"{where}: {hex(value_o)} -> {hex(value_v)}")
            probes.pop("gas_readings", None)
            predictions_differ = probes.pop("create2_predictions", []) != original_probes.get("create2_predictions", [])
            created_code_differs = any(item.endswith(".code") and item.split(".")[0] in created_o | created_v
                                       for item in structural)
            create2_addresses_differ = (probes.get("create2", 0) > 0 and created_o != created_v) or \
                predictions_differ or created_code_differs
            if create2_addresses_differ:
                # Contracts created (or their CREATE2 addresses predicted) from initcode embedded in the code: their
                # code and addresses, and everything that depends on them, differ with any recompilation
                klass = "code (embedded initcode)" + (", status" if outcome["status"] != original["status"] else "")
            elif outcome["status"] != original["status"]:
                klass = "status (also with a warm access list)" if warm_status_changes else "status"
            elif not unexplained and all(item in gas_dependent_words for item in structural):
                explained_gas += structural
                klass = "+".join(name for name, items in (("gas", explained_gas), ("code", explained_code)) if items)
            elif not structural and words and {family(word_kind(where)) for where, _, _ in words} <= \
                    {family(word_kind(where)) for where in gas_dependent_words | set(own_limit_words)}:
                # Every differing word is of a kind that the perturbations of the original change in this same
                # transaction (the same slots, the same word of the logs), only at other positions: e.g. a loop
                # bounded by the gas left processes another number of items
                klass = "gas (the perturbations change the same kinds of words)"
            elif variant == "grey" and same_as_solc:
                klass = "same as solc"
            else:
                klass = "UNEXPLAINED"
            rows.append({"address": address, "hash": transaction_hash, "variant": variant, "class": klass,
                         "status_original": original["status"], "status_variant": outcome["status"],
                         "gas_original": original["gas_used"], "gas_variant": outcome["gas_used"],
                         "differing_words": len(words), "structural": "; ".join(structural[:4]),
                         "word_kinds": " ".join(sorted({word_kind(where) for where, _, _ in words})),
                         "explained_gas": len(explained_gas), "explained_code": len(explained_code),
                         "unexplained": "; ".join(unexplained[:4]), "grey_same_as_solc": same_as_solc,
                         "original_limit_sensitive": limit_sensitive, "warm_changes_words": len(gas_dependent_words),
                         "warm_error": warm["error"][:80] if warm["error"] else "",
                         "warm_word_kinds": " ".join(sorted({word_kind(w) for w in gas_dependent_words})),
                         "own_limit_word_kinds": " ".join(sorted({word_kind(w) for w in own_limit_words})),
                         "created_original": " ".join(sorted(created_o)), "created_variant": " ".join(sorted(created_v)),
                         **probes})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("data_dir", type=Path)
    parser.add_argument("replay_dir", type=Path, help="Output of gas_offline_replay.py replay")
    parser.add_argument("--variants-dir", type=Path, dest="variants_dir", required=True)
    parser.add_argument("--variants", type=lambda value: value.split(","), default=["solc", "grey"])
    parser.add_argument("--t8n", required=True)
    parser.add_argument("--fork", default="Prague")
    parser.add_argument("--out-dir", type=Path, dest="out_dir", required=True)
    parser.add_argument("--per-contract", type=int, dest="per_contract", default=None,
                        help="Mismatching transactions diagnosed per contract (default: all)")
    parser.add_argument("--jobs", type=int, default=None)
    args = parser.parse_args()
    args.t8n = str(Path(args.t8n).resolve()) if "/" in args.t8n else (shutil.which(args.t8n) or args.t8n)

    executions = pd.read_csv(args.replay_dir.joinpath("transactions.csv.gz"))
    valid = set(executions[(executions.variant == "receipt") & (executions.valid == True)].hash)
    mismatching = executions[executions.variant.isin(args.variants) & (executions.matches_original == False) &
                             executions.hash.isin(valid)][["address", "hash"]].drop_duplicates()
    if args.per_contract:
        mismatching = mismatching.groupby("address").head(args.per_contract)
    print(f"{len(mismatching)} mismatching transactions in {mismatching.address.nunique()} contracts", flush=True)
    with ProcessPoolExecutor(max_workers=args.jobs or jobs_from_load()) as executor:
        futures = [executor.submit(diagnose_transaction, row.address, row.hash, args.data_dir, args.variants_dir,
                                   args.variants, args.t8n, args.fork) for row in mismatching.itertuples()]
        rows = [row for future in futures for row in future.result()]
    args.out_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows)
    # Consolidation: an unexplained transaction whose differing words are of the same kinds as those of transactions of
    # the same contract and function explained by the gas (the perturbation may not reach the measured span of every
    # transaction) gets their class
    buckets = executions[executions.variant == "receipt"].set_index("hash").bucket
    frame["bucket"] = frame.hash.map(buckets)
    if "word_kinds" in frame:
        gas_kinds = frame[frame["class"] == "gas"].groupby(["address", "bucket", "variant"]).word_kinds.agg(set)
        for index, row in frame[frame["class"] == "UNEXPLAINED"].iterrows():
            kinds = gas_kinds.get((row.address, row.bucket, row.variant), set())
            if isinstance(row.word_kinds, str) and row.word_kinds in kinds:
                frame.loc[index, "class"] = "gas (same words as the function's gas-explained transactions)"
    frame.to_csv(args.out_dir.joinpath("transactions.csv"), index=False)
    lines = []
    for address, group in frame.groupby("address"):
        classes = {variant: dict(rows["class"].value_counts()) for variant, rows in group.groupby("variant")}
        probes = group[group.variant == "grey"] if "grey" in set(group.variant) else group
        lines.append(f"{address} {classes} | grey = solc {dict(probes.grey_same_as_solc.value_counts())} | "
                     f"original depends on the gas limit {int(probes.original_limit_sensitive.sum())}/{len(probes)} | "
                     f"GAS {int(probes.get('gas_ops', pd.Series([0])).sum())}, all-gas calls "
                     f"{int(probes.get('all_gas_calls', pd.Series([0])).sum())}, own code ops "
                     f"{int(probes.get('own_code_ops', pd.Series([0])).sum())}, ext code ops "
                     f"{int(probes.get('external_code_ops', pd.Series([0])).sum())}, CREATE2 "
                     f"{int(probes.get('create2', pd.Series([0])).sum())}")
        unexplained = group[group["class"] == "UNEXPLAINED"].unexplained.dropna()
        if len(unexplained):
            lines.append(f"    e.g. {unexplained.iloc[0][:200]}")
    summary = "\n".join(lines)
    args.out_dir.joinpath("summary.txt").write_text(summary + "\n")
    print(summary)
    accounting = account_transactions(executions, frame, args.variants)
    accounting.to_csv(args.out_dir.joinpath("accounting.csv"), index=False)
    table = accounting.groupby("category").agg(transactions=("hash", "size"), contracts=("address", "nunique"))
    table = table.sort_values("transactions", ascending=False)
    args.out_dir.joinpath("accounting.txt").write_text(table.to_string() + f"\ntotal {len(accounting)}\n")
    print("\nWhere every sampled transaction goes:\n" + table.to_string() + f"\ntotal {len(accounting)}")


def account_transactions(executions: pd.DataFrame, diagnosis: pd.DataFrame, variants: List[str]) -> pd.DataFrame:
    """
    One category per sampled transaction: compared (every variant matches the original), a variant without code but
    the others match, a mismatch with its class (from the diagnosis), an exclusion (the error of the variants'
    execution), or a receipt that could not be reproduced
    """
    reference, other = variants[0], variants[-1]
    receipts = executions[executions.variant == "receipt"].set_index("hash")
    by_variant = {variant: executions[executions.variant == variant].set_index("hash") for variant in variants}
    classes = diagnosis[diagnosis.variant == other].set_index("hash")["class"] if len(diagnosis) else pd.Series()
    rows = []
    for transaction_hash, receipt in receipts.iterrows():
        if receipt.valid != True:
            category = "receipt not reproduced"
        else:
            errors = {v: by_variant[v].error.get(transaction_hash) for v in variants}
            errors = {v: e if isinstance(e, str) and e else "" for v, e in errors.items()}
            matches = {v: by_variant[v].matches_original.get(transaction_hash) == True for v in variants}
            if errors[other]:
                category = "excluded: " + errors[other].removeprefix("no code: ").split(" (")[0]
            elif errors[reference] and matches[other]:
                category = f"{reference} has no code; {other} matches the original"
            elif all(matches.values()):
                category = "compared (every variant matches the original)"
            else:
                klass = classes.get(transaction_hash, "?")
                kind = "gas-dependent" if klass.startswith("gas") else \
                    "code-dependent" if klass.startswith("code") else klass
                category = f"mismatch with the original, {kind}" + \
                    (f"; {reference} has no code" if errors[reference] else "")
        rows.append({"address": receipt.address, "hash": transaction_hash, "category": category})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    main()
