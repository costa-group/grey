#!/usr/bin/env python3
"""
Offline replay of the sampled mainnet transactions (evaluation/scripts/run_mainnet_gas_evaluation.sh, steps after
`prestate`) with a state transition tool (t8n): `evmone t8n` on grey-remote (evaluation/scripts/install_evmone.sh), or geth's
`evm t8n` (same input format).
No RPC is needed: every transaction carries its prestate (the accounts and storage slots it reads, as they were right
before it), its signed form, its receipt and its block header (gas_mainnet_replay.py fetch-prestate).

Stages:
  resolve-etherscan <data_dir> [--solc-cache DIR]
      For the contracts whose source came from Etherscan (not on Sourcify: no immutable values): recompiles the
      original input with the original compiler, finds which on-chain code it is (the contract's own, or the
      implementation of a proxy: Etherscan returns the implementation's source for minimal clones and ERC-1967
      proxies) and reads the immutables there. Updates deploy/<address>.json.gz (code_address, proxy_kind,
      source_match, immutables) and writes <data_dir>/etherscan_resolution.csv. Run it before `codes`.
  codes <data_dir> <results_dir> --inputs-from F --solc S --variant NAME=ARTIFACT ...
      Runtime code per contract and variant: the deployed code given by the compiler (solc compiling the input, or the
      importer re-importing grey's kept assembly), with the on-chain values of the immutables (Sourcify, in
      deploy/<address>.json.gz) written at its immutable references. No constructor is executed.
      Writes <data_dir>/variants/<NAME>/<address>.json.gz.
  replay <data_dir> --variants NAME,... --t8n BINARY [--engine evmone|geth] --out-dir D [--jobs N]
      Per transaction, four executions with the same prestate:
        - "receipt": the original code under the fork of its block; its gas and status must equal the receipt
          (this validates the prestate and the environment); its logs must equal the receipt's;
        - "original", and each variant (its code at the contract's address, or at the implementation for proxies
          resolved by resolve-etherscan), under --fork (Prague by default, so
          that every transaction and variant uses the same rules).
      A variant matches when its status, logs and resulting state (storage, nonces, codes except the contract's, and
      balances except the sender's and the coinbase's, which depend on the gas) equal the original's under --fork.
      Writes <out>/transactions.csv.gz.
  report <out_dir> <data_dir>
      Totals per variant over the transactions valid and matching for every variant: plain, and weighted by the
      frequency of each bucket (transactions of the bucket in the period / transactions sampled from it).
"""

import argparse
import gzip
import hashlib
import itertools
import json
import os
import re
import shutil
import urllib.request
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from gas_common import input_info_for, jobs_from_load, patch_immutables, variant_runtime_code
from gas_mainnet_replay import ADDRESS_PATTERN, CORPUS_FOLDER, ETHERSCAN_FOLDER, JsonRpc, read_json_gz, write_json_gz

# Mainnet forks that change the EVM, by block number (before the Merge) or timestamp (after). The names are the
# ones of evmone-t8n and geth's t8n (both accept these). MuirGlacier, ArrowGlacier and GrayGlacier only move the
# difficulty bomb, so their blocks use the EVM of the previous fork
FORKS_BY_BLOCK = [(0, "Istanbul"), (12_244_000, "Berlin"), (12_965_000, "London"), (15_537_394, "Merge")]
FORKS_BY_TIMESTAMP = [(1_681_338_455, "Shanghai"), (1_710_338_135, "Cancun"), (1_746_612_311, "Prague"),
                      (1_764_798_551, "Osaka")]
FORK_ORDER = ["Istanbul", "Berlin", "London", "Merge", "Shanghai", "Cancun", "Prague", "Osaka"]
# Fields of the RPC transaction that are not part of the transaction itself
NON_TRANSACTION_FIELDS = {"blockHash", "blockNumber", "blockTimestamp", "transactionIndex"}
# Proxies: the storage slot of the implementation (ERC-1967), and minimal clones (EIP-1167, Solady's LibClone and
# similar), whose short code delegates to a fixed address: PUSH20 <implementation> GAS DELEGATECALL
ERC1967_IMPLEMENTATION_SLOT = "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"
CLONE_DELEGATECALL_PATTERN = re.compile(r"73([0-9a-f]{40})5af4")
MAX_CLONE_SIZE = 100
# Hash in the CBOR metadata that solc appends: {"ipfs": <34-byte multihash>, ...} (≥ 0.6) or {"bzzr0"/"bzzr1":
# <32 bytes>, ...} (older)
METADATA_HASH_PATTERN = re.compile(r"(?:646970667358221220|65627a7a72(?:30|31)5820)([0-9a-f]{64})")
# Official solc builds, used to recompile the Etherscan-verified inputs with their original compiler
SOLC_BINARIES_URL = "https://binaries.soliditylang.org/linux-amd64"


def signed_transaction(transaction: Dict) -> Dict:
    """
    The transaction as t8n reads it: the RPC object without the fields of its inclusion, and only the fee fields of
    its type (the RPC also gives the effective gasPrice of EIP-1559 transactions, which evmone rejects)
    """
    signed = {key: value for key, value in transaction.items() if key not in NON_TRANSACTION_FIELDS}
    # evmone takes the sender from the transaction object instead of recovering it from the signature
    signed["sender"] = signed["from"] = transaction["from"]
    # evmone reads the signature of each EIP-7702 authorization as v (the RPC gives yParity)
    if signed.get("authorizationList"):
        signed["authorizationList"] = [{**authorization, "v": authorization.get("v", authorization.get("yParity"))}
                                       for authorization in signed["authorizationList"]]
    if int(signed.get("type", "0x0"), 16) >= 2:
        signed.pop("gasPrice", None)
    else:
        signed.pop("maxFeePerGas", None)
        signed.pop("maxPriorityFeePerGas", None)
    return signed


def fork_of(block: Dict) -> str:
    number, timestamp = int(block["number"], 16), int(block["timestamp"], 16)
    fork = next(name for start, name in reversed(FORKS_BY_BLOCK) if number >= start)
    for start, name in FORKS_BY_TIMESTAMP:
        if timestamp >= start:
            fork = name
    return fork


def at_least(fork: str, reference: str) -> bool:
    return FORK_ORDER.index(fork) >= FORK_ORDER.index(reference)


# ---------------------------------------------------------------- codes

def contract_name(address: str, deploy_info: Dict) -> Optional[str]:
    etherscan_file = ETHERSCAN_FOLDER.joinpath(f"{address}.json")
    if etherscan_file.is_file():
        return json.loads(etherscan_file.read_text()).get("ContractName") or deploy_info.get("contract")
    return deploy_info.get("contract")


def variant_code_for(address: str, source: Path, data_dir: Path, artifacts_dir: Path, variant: str, artifact: str,
                     solc: Path, depth: int, variants_dir: Path) -> Dict:
    output_file = variants_dir.joinpath(variant, f"{address}.json.gz")
    if output_file.is_file():
        return read_json_gz(output_file)
    deploy_file = data_dir.joinpath("deploy", f"{address}.json.gz")
    deploy_info = read_json_gz(deploy_file) if deploy_file.is_file() else {}
    contract = contract_name(address, deploy_info)
    result = {"address": address, "variant": variant, "contract": contract, "runtime": None, "error": ""}
    try:
        runtime, references, error = variant_runtime_code(artifacts_dir, artifact, input_info_for(source, solc),
                                                          contract, solc, depth, etherscan_libraries(address))
    except Exception as exception:
        runtime, references, error = None, None, f"{type(exception).__name__}: {exception}"
    if runtime is not None:
        onchain_values, values_error = deploy_info.get("immutables") or {}, "no on-chain values of the immutables"
        if deploy_info.get("immutables_error"):
            onchain_values, values_error = {}, f"immutables: {deploy_info['immutables_error'][:80]}"
        elif "immutables_by_our_id" in deploy_info:
            # Keyed by our AST ids (resolve-immutables), so matched by id, never by order: every reference needs its
            # value, and the values of declarations that this code does not reference are left out
            by_our_id = deploy_info["immutables_by_our_id"]
            missing = sorted(set(references or {}) - set(by_our_id), key=int)
            onchain_values = {our_id: by_our_id[our_id] for our_id in references or {} if our_id in by_our_id}
            if missing:
                onchain_values, values_error = {}, f"no on-chain value for the immutables {missing[:3]}"
        if references:
            patched, changed, patch_error = patch_immutables("0x" + runtime, references, onchain_values) \
                if onchain_values else (None, 0, values_error)
            if patched is None:
                runtime, error = None, patch_error
            else:
                runtime = patched
                result["immutables_written"] = len(references)
        else:
            runtime = "0x" + runtime
    result.update(runtime=runtime, error=error)
    write_json_gz(output_file, result)
    return result


def etherscan_libraries(address: str) -> Dict[str, Dict[str, str]]:
    """
    The libraries of Etherscan's Library field ("Name:0xaddress", several separated by ';'), as {"": {name:
    address}} (matched by name when linking)
    """
    etherscan_file = ETHERSCAN_FOLDER.joinpath(f"{address}.json")
    field = (json.loads(etherscan_file.read_text()).get("Library") or "") if etherscan_file.is_file() else ""
    libraries = {}
    for entry in field.split(";"):
        name, _, library_address = entry.strip().partition(":")
        if name and library_address.startswith("0x"):
            libraries[name] = library_address
    return {"": libraries} if libraries else {}


def stage_codes(args) -> None:
    sources = {ADDRESS_PATTERN.search(line).group(0).lower(): Path(line.strip())
               for line in args.inputs_from.read_text().splitlines() if ADDRESS_PATTERN.search(line)}
    addresses = sorted(path.name.split(".")[0] for path in args.data_dir.joinpath("txs").glob("*.json.gz"))
    artifacts_dir = args.results_dir.joinpath("artifacts")
    jobs = args.jobs or jobs_from_load()
    with ProcessPoolExecutor(max_workers=jobs) as executor:
        futures = [executor.submit(variant_code_for, address, sources[address], args.data_dir, artifacts_dir, name,
                                   artifact, args.solc.resolve(), args.depth, variants_dir(args))
                   for address in addresses if address in sources for name, artifact in args.variants]
        results = [future.result() for future in futures]
    frame = pd.DataFrame(results)
    print(frame.groupby("variant").apply(lambda rows: f"{rows.runtime.notna().sum()} codes, errors "
                                         f"{dict(rows[rows.runtime.isna()].error.str[:60].value_counts())}"
                                         ).to_string())


def variants_dir(args) -> Path:
    """
    Folder of the runtime codes per variant: <data_dir>/variants by default; one per compilation (--variants-dir), so
    that the codes of different compilations are not mixed (the codes stage skips the existing files)
    """
    return args.variants_dir or args.data_dir.joinpath("variants")


# ---------------------------------------------------------------- resolve-etherscan

def implementation_of(address: str, prestate: Dict, codes: "CodeStore") -> Tuple[Optional[str], str]:
    """
    The implementation a proxy at the address delegates to in this prestate, and the kind of proxy: the address of a
    minimal clone (fixed in its code), or the ERC-1967 slot (read by the proxy, so present in the prestate).
    (None, "") if the address is not a proxy of these kinds
    """
    account = next((account for key, account in prestate.items() if key.lower() == address), None) or {}
    code = codes.get(account["code"])[2:].lower() if account.get("code") else ""
    match = CLONE_DELEGATECALL_PATTERN.search(code)
    if match and len(code) // 2 <= MAX_CLONE_SIZE:
        return "0x" + match.group(1), "clone"
    slot_value = {key.lower(): value for key, value in (account.get("storage") or {}).items()}.get(
        ERC1967_IMPLEMENTATION_SLOT)
    if slot_value is not None and int(slot_value, 16) != 0:
        return "0x" + slot_value[-40:].lower(), "erc1967"
    return None, ""


def code_in_prestate(address: str, prestate: Dict, codes: "CodeStore") -> Optional[str]:
    account = next((account for key, account in prestate.items() if key.lower() == address), None) or {}
    return codes.get(account["code"])[2:].lower() if account.get("code") else None


def solc_binary(version: str, cache_dir: Path) -> Path:
    """
    The official solc <version> (e.g. 0.8.25): solc-select's copy if installed, otherwise downloaded once from
    binaries.soliditylang.org into cache_dir and checked against the sha256 of its list
    """
    installed = Path.home().joinpath(".solc-select", "artifacts", f"solc-{version}", f"solc-{version}")
    # An installed copy may be broken (e.g. a truncated download that segfaults): it must at least run
    if installed.is_file() and subprocess.run([str(installed), "--version"], capture_output=True).returncode == 0:
        return installed
    binary = cache_dir.joinpath(f"solc-{version}")
    if not binary.is_file():
        # The server rejects urllib's default User-Agent (HTTP 403)
        headers = {"User-Agent": "grey-gas-evaluation"}
        with urllib.request.urlopen(urllib.request.Request(f"{SOLC_BINARIES_URL}/list.json", headers=headers),
                                    timeout=60) as response:
            build = next(build for build in json.load(response)["builds"] if build["version"] == version)
        with urllib.request.urlopen(urllib.request.Request(f"{SOLC_BINARIES_URL}/{build['path']}", headers=headers),
                                    timeout=300) as response:
            content = response.read()
        if "0x" + hashlib.sha256(content).hexdigest() != build["sha256"]:
            raise ValueError(f"sha256 mismatch for solc {version}")
        cache_dir.mkdir(parents=True, exist_ok=True)
        binary.write_bytes(content)
        binary.chmod(0o755)
    return binary


def etherscan_standard_input(etherscan_info: Dict) -> Dict:
    """
    The original compiler input of an Etherscan-verified contract: its standard JSON ('{{...}}' or '{...}'), or a
    single source file with the settings Etherscan lists
    """
    source = etherscan_info["SourceCode"].strip()
    if source.startswith("{{"):
        return json.loads(source[1:-1])
    if source.startswith("{"):
        parsed = json.loads(source)
        return parsed if "sources" in parsed else {"language": "Solidity", "sources": parsed, "settings": {}}
    settings = {"optimizer": {"enabled": etherscan_info.get("OptimizationUsed") == "1",
                              "runs": int(etherscan_info.get("Runs") or 200)}}
    if etherscan_info.get("EVMVersion", "Default").lower() not in ("", "default"):
        settings["evmVersion"] = etherscan_info["EVMVersion"].lower()
    return {"language": "Solidity", "sources": {f"{etherscan_info['ContractName']}.sol": {"content": source}},
            "settings": settings}


def immutable_declarations(solc_output: Dict, function_typed: Optional[set] = None) -> Dict[str, str]:
    """
    AST id -> "Contract.variable" of every immutable declared in the sources of a solc standard JSON output (with the
    "ast" output selected). The ids of the immutables of internal function type are added to function_typed
    """
    names: Dict[str, str] = {}

    def visit(node, contract: Optional[str]) -> None:
        if isinstance(node, dict):
            if node.get("nodeType") == "ContractDefinition":
                contract = node["name"]
            if node.get("nodeType") == "VariableDeclaration" and node.get("mutability") == "immutable":
                names[str(node["id"])] = f"{contract}.{node['name']}"
                type_string = (node.get("typeDescriptions") or {}).get("typeString") or ""
                if function_typed is not None and type_string.startswith("function ") and "external" not in type_string:
                    function_typed.add(str(node["id"]))
            for child in node.values():
                visit(child, contract)
        elif isinstance(node, list):
            for child in node:
                visit(child, contract)

    for source in solc_output.get("sources", {}).values():
        visit(source.get("ast"), None)
    return names


def corpus_immutable_names(corpus_input: Path, solc: Path, function_typed: Optional[set] = None) -> Dict[str, str]:
    """
    AST id -> "Contract.variable" of the immutables in the corpus input, numbered as in the variants' compilations
    (same input and compiler); the ids of internal function type go to function_typed. The ids are assigned by the
    parser, but the types need the analysis (stopAfter parsing leaves typeDescriptions empty), so the full AST is
    requested
    """
    standard_input = json.loads(corpus_input.read_text())
    settings = standard_input.setdefault("settings", {})
    settings["outputSelection"] = {"*": {"": ["ast"]}}
    if function_typed is None:
        # Only the names: parsing is enough. stopAfter cannot be combined with the code generation settings
        settings["stopAfter"] = "parsing"
        for key in ("viaIR", "optimizer", "libraries"):
            settings.pop(key, None)
    with tempfile.TemporaryDirectory(prefix="gas_corpus_") as work:
        input_file = Path(work, "input.json")
        input_file.write_text(json.dumps(standard_input))
        completed = subprocess.run([str(solc), "--standard-json", str(input_file)], capture_output=True, text=True,
                                   cwd=work)
    return immutable_declarations(json.loads(completed.stdout), function_typed)


def compile_original(etherscan_info: Dict, cache_dir: Path) -> Tuple[List[Dict], str]:
    """
    Deployed code and immutable references of every contract named as the verified one, compiled from the original
    input with the original compiler (the corpus inputs were rewritten for the experiments: pragma, viaIR, runs and
    metadata, so they do not reproduce the deployed code). Each entry also carries "immutable_names" (AST id ->
    "Contract.variable" in this compilation)
    """
    version = etherscan_info["CompilerVersion"].lstrip("v").split("+")[0]
    standard_input = etherscan_standard_input(etherscan_info)
    standard_input.setdefault("settings", {})["outputSelection"] = {
        "*": {"*": ["evm.deployedBytecode.object", "evm.deployedBytecode.immutableReferences"], "": ["ast"]}}
    with tempfile.TemporaryDirectory(prefix="gas_etherscan_") as work:
        input_file = Path(work, "input.json")
        input_file.write_text(json.dumps(standard_input))
        completed = subprocess.run([str(solc_binary(version, cache_dir)), "--standard-json", str(input_file)],
                                   capture_output=True, text=True, cwd=work)
    output = json.loads(completed.stdout)
    errors = [error.get("formattedMessage", error.get("message", ""))[:200]
              for error in output.get("errors", []) if error.get("severity") == "error"]
    if errors:
        return [], f"solc {version}: {errors[0]}"
    names = immutable_declarations(output)
    compiled = [{**contract["evm"]["deployedBytecode"], "immutable_names": names}
                for contracts in output.get("contracts", {}).values()
                for name, contract in contracts.items() if name == etherscan_info["ContractName"]]
    return compiled, "" if compiled else f"solc {version}: no contract {etherscan_info['ContractName']}"


def masked_code(code: str, references: Dict[str, List[Dict]], mask_metadata: bool) -> bytes:
    """
    The code with the immutables zeroed and, with mask_metadata, the hashes of every CBOR metadata block (the
    contract's, at the end, and the ones of the creation codes it embeds for `new`). The metadata hash changes with
    any change of the source files, even in comments or paths, without changing the executable code
    """
    masked = bytearray.fromhex(code)
    for places in references.values():
        for place in places:
            masked[place["start"]:place["start"] + place["length"]] = bytes(place["length"])
    if mask_metadata:
        for match in METADATA_HASH_PATTERN.finditer(code):
            if match.start(1) % 2 == 0:
                start, end = match.start(1) // 2, match.end(1) // 2
                masked[start:end] = bytes(end - start)
    return bytes(masked)


def immutable_values(onchain_code: str, references: Dict[str, List[Dict]]) -> Optional[Dict[str, str]]:
    """
    The value of each immutable (AST id -> 32-byte word, as Sourcify gives them) read from the on-chain code; None if
    the places of one immutable disagree
    """
    code = bytes.fromhex(onchain_code)
    values = {}
    for ast_id, places in references.items():
        read = {code[place["start"]:place["start"] + place["length"]].hex() for place in places}
        if len(read) != 1:
            return None
        values[ast_id] = "0x" + read.pop().rjust(64, "0")
    return values


def resolve_etherscan_contract(deploy_file: Path, data_dir: Path, cache_dir: Path) -> Dict:
    """
    For a contract whose source came from Etherscan (not on Sourcify, so without immutable values): finds which code
    the verified source is (the contract's own, or, for proxies, the implementation the proxy delegates to: Etherscan
    returns the implementation's source for them), and reads the immutables from that on-chain code. Records in the
    deploy file:
      - code_address: where the variants' code must be placed (the implementation for proxies);
      - proxy_kind: "clone" / "erc1967" / "" (not a proxy). An upgraded proxy delegates to other implementations in
        some transactions: the replay excludes them;
      - source_match: "exact", or "partial" when only the metadata hashes differ;
      - immutables (only if empty) and immutables_source "etherscan-recompiled";
      - resolution_error if the recompiled code matches no candidate code.
    """
    deploy_info = read_json_gz(deploy_file)
    address = deploy_info["address"]
    summary = {"address": address, "code_address": None, "proxy_kind": "", "matched": 0, "transactions": 0,
               "immutables": 0, "match": "", "error": ""}
    etherscan_file = ETHERSCAN_FOLDER.joinpath(f"{address}.json")
    txs_file = data_dir.joinpath("txs", f"{address}.json.gz")
    if not etherscan_file.is_file() or not txs_file.is_file():
        summary["error"] = "no Etherscan source or no transactions"
        return summary
    etherscan_info = json.loads(etherscan_file.read_text())
    codes = CodeStore(data_dir.joinpath("codes"))
    # Candidate code per transaction: the implementation for proxies, the contract's own code otherwise
    # (code address, proxy kind) -> [transactions, on-chain code]
    candidates: Dict[Tuple[str, str], List] = {}
    for data in read_json_gz(txs_file).get("prestate_data") or []:
        implementation, kind = implementation_of(address, data["prestate"], codes)
        # The contract's own code is always a candidate: the verified source can be the proxy itself
        for key in dict.fromkeys([(implementation or address, kind), (address, "")]):
            candidate = candidates.setdefault(key, [0, None])
            candidate[0] += 1
            candidate[1] = candidate[1] or code_in_prestate(key[0], data["prestate"], codes)
    summary["transactions"] = candidates[(address, "")][0] if (address, "") in candidates else 0
    compiled, error = compile_original(etherscan_info, cache_dir)
    resolved = None
    for (code_address, kind), (count, onchain) in sorted(candidates.items(), key=lambda item: -item[1][0]):
        if onchain is None:
            continue
        # An exact match first (the metadata too), then a partial one (only the metadata hashes differ)
        for mask_metadata, deployed in itertools.product([False, True], compiled):
            references = deployed.get("immutableReferences") or {}
            if len(deployed["object"]) == len(onchain) and masked_code(deployed["object"], references, mask_metadata) \
                    == masked_code(onchain, references, mask_metadata):
                values = immutable_values(onchain, references)
                if values is not None:
                    resolved = (code_address, kind, count, values, "partial" if mask_metadata else "exact")
                    break
        if resolved:
            break
    if resolved is None:
        summary["error"] = error or "the recompiled code matches no candidate code"
        deploy_info["resolution_error"] = summary["error"]
    else:
        code_address, kind, count, values, match = resolved
        summary.update(code_address=code_address, proxy_kind=kind, matched=count, immutables=len(values), match=match)
        deploy_info.pop("resolution_error", None)
        deploy_info.update(code_address=code_address, proxy_kind=kind, source_match=match)
        if not deploy_info.get("immutables") and values:
            deploy_info["immutables"], deploy_info["immutables_source"] = values, "etherscan-recompiled"
    write_json_gz(deploy_file, deploy_info)
    return summary


# An immutable of internal function type holds a compiler-specific value (a code offset in the legacy pipeline, an
# internal id in via-IR): the on-chain value means nothing in the variants' code, which would call an invalid function
# (StakingPool: Panic 0x51). Only running each variant's own constructor would give its value, so they are excluded
FUNCTION_POINTER_ERROR = "internal function pointers in immutables (compiler-specific values)"


def resolve_immutables_contract(deploy_file: Path, data_dir: Path, corpus_dir: Path, solc: Path,
                                cache_dir: Path) -> Dict:
    """
    Keys the on-chain values of the immutables by the AST ids of the variants' compilations (the corpus input), so
    that `codes` writes each value at the references of its own declaration. Sourcify's values are keyed by the ids of
    Sourcify's compilation, which number the declarations differently when its source paths or order differ (XONE:
    ERC20Capped._cap first there, last in ours), so matching the ids by their order shifts the values. When the ids
    differ, the values are read again from the on-chain code at the references of a recompilation of the original
    input with the original compiler (exact match or up to the metadata hashes, at code_address for proxies) and
    matched by declaration ("Contract.variable"). Records immutables_by_our_id (or immutables_error) in the deploy
    file. Contracts whose code uses an immutable of internal function type get an immutables_error (see
    FUNCTION_POINTER_ERROR)
    """
    deploy_info = read_json_gz(deploy_file)
    address = deploy_info["address"]
    summary = {"address": address, "immutables": len(deploy_info.get("immutables") or {}), "method": "", "error": ""}
    corpus_input = corpus_dir.joinpath(address, f"{address}_standard_input.json")
    function_typed: set = set()
    ours = corpus_immutable_names(corpus_input, solc, function_typed) if corpus_input.is_file() else {}
    deploy_info.pop("immutables_by_our_id", None)
    deploy_info.pop("immutables_error", None)
    onchain_ids = set(deploy_info.get("immutables") or {})
    if onchain_ids <= set(ours):
        # Same numbering: the values can be used as they are
        summary["method"] = "same ids"
        if onchain_ids & function_typed:
            deploy_info["immutables_error"] = summary["error"] = FUNCTION_POINTER_ERROR + \
                f" ({', '.join(sorted(ours[our_id] for our_id in onchain_ids & function_typed))})"
        write_json_gz(deploy_file, deploy_info)
        return summary
    # Our names must be unique to be matched (the same contract name in two files would be ambiguous)
    ours_by_name: Dict[str, str] = {}
    for our_id, name in ours.items():
        ours_by_name[name] = None if name in ours_by_name else our_id
    error, by_our_id = "", None
    etherscan_file = ETHERSCAN_FOLDER.joinpath(f"{address}.json")
    txs_file = data_dir.joinpath("txs", f"{address}.json.gz")
    if not etherscan_file.is_file() or not txs_file.is_file():
        error = "no original input or no transactions"
    else:
        codes = CodeStore(data_dir.joinpath("codes"))
        code_address = deploy_info.get("code_address") or address
        onchain = next((code for code in (code_in_prestate(code_address, data["prestate"], codes)
                                          for data in read_json_gz(txs_file).get("prestate_data") or []) if code), None)
        compiled, error = compile_original(json.loads(etherscan_file.read_text()), cache_dir)
        if onchain is None:
            error = error or "no on-chain code in the prestates"
        else:
            for mask_metadata, deployed in itertools.product([False, True], compiled):
                references = deployed.get("immutableReferences") or {}
                if len(deployed["object"]) != len(onchain) or masked_code(deployed["object"], references, mask_metadata) \
                        != masked_code(onchain, references, mask_metadata):
                    continue
                values = immutable_values(onchain, references)
                if values is None:
                    continue
                by_our_id, missing = {}, []
                for their_id, value in values.items():
                    name = deployed["immutable_names"].get(their_id)
                    our_id = ours_by_name.get(name)
                    if our_id is None:
                        missing.append(name or their_id)
                    else:
                        by_our_id[our_id] = value
                error = f"declarations not found in the corpus input: {missing[:3]}" if missing else ""
                summary["method"] = "recompiled, " + ("partial" if mask_metadata else "exact") + " match"
                break
            else:
                error = error or "the recompiled code matches no on-chain code"
    if by_our_id is not None and not error and set(by_our_id) & function_typed:
        error = FUNCTION_POINTER_ERROR + f" ({', '.join(sorted(ours[i] for i in set(by_our_id) & function_typed))})"
    if by_our_id is not None and not error:
        deploy_info["immutables_by_our_id"] = by_our_id
    else:
        deploy_info["immutables_error"] = summary["error"] = error
    write_json_gz(deploy_file, deploy_info)
    return summary


def stage_resolve_immutables(args) -> None:
    deploy_files = [path for path in sorted(args.data_dir.joinpath("deploy").glob("*.json.gz"))
                    if read_json_gz(path).get("immutables")]
    solc = args.solc.resolve()
    with ProcessPoolExecutor(max_workers=args.jobs or jobs_from_load()) as executor:
        summaries = list(executor.map(resolve_immutables_contract, deploy_files,
                                      [args.data_dir] * len(deploy_files), [args.corpus_dir] * len(deploy_files),
                                      [solc] * len(deploy_files), [args.solc_cache] * len(deploy_files)))
    frame = pd.DataFrame(summaries)
    frame.to_csv(args.data_dir.joinpath("immutables_resolution.csv"), index=False)
    print(frame.groupby(["method", "error"]).size().to_string())
    print(frame[frame.method != "same ids"].to_string(index=False))


def stage_resolve_etherscan(args) -> None:
    deploy_files = [path for path in sorted(args.data_dir.joinpath("deploy").glob("*.json.gz"))
                    if read_json_gz(path).get("source") != "sourcify"]
    summaries = [resolve_etherscan_contract(path, args.data_dir, args.solc_cache) for path in deploy_files]
    frame = pd.DataFrame(summaries)
    print(frame.to_string(index=False))
    frame.to_csv(args.data_dir.joinpath("etherscan_resolution.csv"), index=False)


# ---------------------------------------------------------------- replay

class CodeStore:
    """
    Codes of the prestates, stored once by sha256 in <data_dir>/codes (gas_mainnet_replay.store_code)
    """

    def __init__(self, codes_dir: Path):
        self.codes_dir, self.cache = codes_dir, {}

    def get(self, reference: str) -> str:
        if not reference.startswith("sha256:"):
            return reference
        if reference not in self.cache:
            with gzip.open(self.codes_dir.joinpath(f"{reference[len('sha256:'):]}.hex.gz"), "rt") as f:
                self.cache[reference] = f.read()
        return self.cache[reference]


def alloc_from_prestate(prestate: Dict, codes: CodeStore, replaced_code: Optional[Tuple[str, str]]) -> Dict:
    """
    The t8n alloc of a prestate, with the code of one account replaced (address, code) for the variants
    """
    alloc = {}
    for address, account in prestate.items():
        # evmone requires every field of every account (geth accepts them missing)
        alloc[address.lower()] = {"balance": account.get("balance", "0x0"),
                                  "nonce": hex(int(account.get("nonce", 0))),
                                  "code": codes.get(account["code"]) if account.get("code") else "0x",
                                  "storage": account.get("storage") or {}}
    if replaced_code is not None:
        address, code = replaced_code
        alloc.setdefault(address, {"balance": "0x0", "nonce": "0x1", "code": "0x", "storage": {}})["code"] = code
    return alloc


def environment(block: Dict, fork: str, block_hashes: Optional[Dict[str, str]] = None,
                neutral_blob_fee: bool = False) -> Dict:
    """
    The t8n environment of the block of a transaction for a fork. For a fork later than the block's (the uniform
    replay), the fields the block lacks get neutral values: prevrandao from mixHash, base fee 7 wei (the minimum,
    below any gas price, and the gas used does not depend on it), no blobs, zero beacon root, no withdrawals.
    block_hashes: the hashes of the older blocks that the transaction reads with BLOCKHASH (fetch-blockhashes); only
    the parent's is in the header, and the tool would answer a made-up value for the others.
    neutral_blob_fee: no excess blob gas (blob base fee 1 wei). Used only to retry a blob transaction (type 3) that the
    tool rejects for its blob fee: evmone does not know the blob parameters of the BPO forks (2026), so it computes a
    fee above maxFeePerBlobGas. The blob fee does not change the execution gas, but programs that read BLOBBASEFEE
    see another value, and the receipt check then fails if it reaches the logs or the state
    """
    number = int(block["number"], 16)
    hashes = {str(number - 1): block["parentHash"], **(block_hashes or {})}
    env = {"currentCoinbase": block["miner"], "currentGasLimit": block["gasLimit"], "currentNumber": block["number"],
           "currentTimestamp": block["timestamp"], "blockHashes": hashes, "parentHash": block["parentHash"]}
    if at_least(fork, "Merge"):
        env["currentRandom"] = block.get("mixHash") or "0x" + "00" * 32
        env["currentDifficulty"] = "0x0"
    else:
        env["currentDifficulty"] = block["difficulty"]
    if at_least(fork, "London"):
        env["currentBaseFee"] = block.get("baseFeePerGas") or "0x7"
    if at_least(fork, "Shanghai"):
        env["withdrawals"] = []
    if at_least(fork, "Cancun"):
        env["currentExcessBlobGas"] = "0x0" if neutral_blob_fee else (block.get("excessBlobGas") or "0x0")
        env["parentBeaconBlockRoot"] = block.get("parentBeaconBlockRoot") or "0x" + "00" * 32
    return env


def run_t8n(t8n: str, engine: str, alloc: Dict, env: Dict, transaction: Dict, fork: str, folder: Path) -> Dict:
    """
    One transaction through the t8n tool; returns its receipt (status, gasUsed, logs), the post state and the error
    (rejected transaction or tool failure)
    """
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    for name, content in [("alloc.json", alloc), ("env.json", env), ("txs.json", [transaction])]:
        folder.joinpath(name).write_text(json.dumps(content))
    # Both geth's evm and the evmone CLI take t8n as a subcommand. No block reward (0 wei): in evmone, -1 means
    # "output the pre-state only"
    command = [t8n, "t8n",
               "--input.alloc", "alloc.json", "--input.env", "env.json", "--input.txs", "txs.json",
               "--output.basedir", ".", "--output.result", "result.json", "--output.alloc", "post.json",
               "--state.fork", fork, "--state.chainid", "1", "--state.reward", "0"]
    completed = subprocess.run(command, capture_output=True, text=True, cwd=folder, timeout=600)
    result_file = folder.joinpath("result.json")
    if completed.returncode != 0 or not result_file.is_file() or result_file.stat().st_size == 0:
        return {"error": f"t8n failed: {(completed.stderr or completed.stdout).strip()[-300:]}"}
    result = json.loads(result_file.read_text())
    if result.get("rejected"):
        return {"error": f"rejected: {str(result['rejected'][0].get('error'))[:200]}"}
    receipt = result["receipts"][0]
    post = json.loads(folder.joinpath("post.json").read_text())
    return {"status": int(receipt["status"], 16), "gas_used": int(receipt["gasUsed"], 16),
            "logs": [(log["address"].lower(), tuple(log["topics"]), log["data"]) for log in receipt.get("logs") or []],
            "post": post, "error": ""}


def comparable_state(post: Dict, ignore_code_of: str, ignore_balance_of: set) -> Dict:
    """
    The post state without what legitimately differs between codes: the code of the replaced account, and the
    balances that pay or receive the gas
    """
    state = {}
    for address, account in post.items():
        address = address.lower()
        entry = {"nonce": account.get("nonce", "0x0"),
                 "storage": {key: value for key, value in (account.get("storage") or {}).items()
                             if int(value, 16) != 0}}
        if address != ignore_code_of:
            entry["code"] = account.get("code", "0x")
        if address not in ignore_balance_of:
            entry["balance"] = account.get("balance", "0x0")
        state[address] = entry
    return state


def raised_gas_limit(transaction: Dict, block: Dict, prestate: Dict) -> Tuple[Dict, Dict]:
    """
    The transaction with the gas limit of its block (if larger), and the prestate with the sender's balance raised to
    pay for it. The signature no longer matches: only for engines that take the sender from the transaction (evmone)
    """
    original_limit, block_limit = int(transaction["gas"], 16), int(block["gasLimit"], 16)
    if block_limit <= original_limit:
        return transaction, prestate
    # Without its hash: evmone checks that it matches the (modified) transaction
    raised = {key: value for key, value in transaction.items() if key != "hash"}
    raised["gas"] = hex(block_limit)
    price = int(transaction.get("maxFeePerGas") or transaction.get("gasPrice") or "0x0", 16)
    sender = transaction["from"].lower()
    prestate = {address: dict(account) for address, account in prestate.items()}
    account = next((account for address, account in prestate.items() if address.lower() == sender), None)
    if account is None:
        account = prestate.setdefault(sender, {"balance": "0x0"})
    account["balance"] = hex(int(account.get("balance", "0x0"), 16) + (block_limit - original_limit) * price)
    return raised, prestate


def replay_contract(txs_file: Path, data_dir: Path, variants: List[str], t8n: str, engine: str, fork: str,
                    raise_gas_limit: bool = True, codes_dir: Optional[Path] = None) -> List[Dict]:
    stored = read_json_gz(txs_file)
    address = stored["address"]
    codes = CodeStore(data_dir.joinpath("codes"))
    buckets = {entry["hash"]: entry.get("bucket") for entry in stored["selected"]}
    # Contracts verified on Etherscan (resolve-etherscan): the code may belong at the implementation of a proxy
    deploy_file = data_dir.joinpath("deploy", f"{address}.json.gz")
    deploy_info = read_json_gz(deploy_file) if deploy_file.is_file() else {}
    code_address = deploy_info.get("code_address") or address
    variant_codes = {}
    for variant in variants:
        variant_file = (codes_dir or data_dir.joinpath("variants")).joinpath(variant, f"{address}.json.gz")
        variant_codes[variant] = read_json_gz(variant_file) if variant_file.is_file() else {"runtime": None,
                                                                                              "error": "no code file"}
    rows = []
    with tempfile.TemporaryDirectory(prefix="gas_t8n_") as work:
        for data in stored.get("prestate_data") or []:
            transaction, receipt, block = data["transaction"], data["receipt"], data["block"]
            base = {"address": address, "hash": transaction["hash"], "bucket": buckets.get(transaction["hash"]),
                    "block": int(block["number"], 16), "own_fork": fork_of(block)}
            signed = signed_transaction(transaction)
            sender, coinbase = transaction["from"].lower(), block["miner"].lower()
            # The variants' code replaces the code that the verified source compiles to: the implementation, for
            # proxies. Transactions of an upgraded proxy that delegate to another implementation are excluded
            skip_variants = ""
            if deploy_info.get("resolution_error"):
                skip_variants = f"no code: {deploy_info['resolution_error']}"
            elif deploy_info.get("proxy_kind") and \
                    implementation_of(address, data["prestate"], codes)[0] != code_address:
                skip_variants = "no code: the proxy delegates to another implementation in this transaction"
            elif code_in_prestate(code_address, data["prestate"], codes) is None:
                # The address had no code yet (e.g. funded before the contract was deployed there): the original
                # transaction executes no code, so the variants' code cannot replace it
                skip_variants = "no code: the address has no code in this transaction"
            executions = [("receipt", base["own_fork"], None), ("original", fork, None)] + \
                [(variant, fork, (code_address, None if skip_variants else variant_codes[variant]["runtime"]))
                 for variant in variants]
            # The uniform executions run with the block's gas limit (raise_gas_limit): the sender sized the limit for
            # the original code, so a variant somewhat more expensive on a tight transaction would run out of gas
            # and be excluded instead of measured. The receipt check keeps the original limit
            raised, raised_prestate = raised_gas_limit(signed, block, data["prestate"]) if raise_gas_limit \
                else (signed, data["prestate"])
            outcomes = {}
            for name, execution_fork, replaced in executions:
                row = {**base, "variant": name, "fork": execution_fork}
                if replaced is not None and replaced[1] is None:
                    rows.append({**row, "error": skip_variants or f"no code: {variant_codes[name]['error'][:100]}"})
                    continue
                uniform = name != "receipt"
                outcome = None
                for neutral_blob_fee in (False, True):
                    try:
                        outcome = run_t8n(t8n, engine,
                                          alloc_from_prestate(raised_prestate if uniform else data["prestate"], codes,
                                                              replaced),
                                          environment(block, execution_fork, data.get("block_hashes"),
                                                      neutral_blob_fee),
                                          raised if uniform else signed, execution_fork, Path(work, name))
                    except Exception as exception:
                        outcome = {"error": f"{type(exception).__name__}: {str(exception)[:200]}"}
                    # Retried with a neutral blob fee only if the tool rejects the blob fee (see environment)
                    if "BLOB_GAS" not in outcome.get("error", ""):
                        break
                outcomes[name] = outcome
                if outcome["error"]:
                    rows.append({**row, "error": outcome["error"]})
                    continue
                row.update(status=outcome["status"], gas_used=outcome["gas_used"], error="")
                if name == "receipt":
                    receipt_logs = [(log["address"].lower(), tuple(log["topics"]), log["data"])
                                    for log in receipt.get("logs") or []]
                    row.update(receipt_gas_used=int(receipt["gasUsed"], 16),
                               valid=outcome["gas_used"] == int(receipt["gasUsed"], 16)
                               and outcome["status"] == int(receipt["status"], 16)
                               and outcome["logs"] == receipt_logs)
                elif name != "original" and not outcomes.get("original", {}).get("error", "missing"):
                    reference = outcomes["original"]
                    ignored_balances = {sender, coinbase}
                    row.update(status_match=outcome["status"] == reference["status"],
                               logs_match=outcome["logs"] == reference["logs"],
                               state_match=comparable_state(outcome["post"], code_address, ignored_balances) ==
                               comparable_state(reference["post"], code_address, ignored_balances))
                    row["matches_original"] = row["status_match"] and row["logs_match"] and row["state_match"]
                rows.append(row)
    return rows


def stage_replay(args) -> None:
    txs_files = sorted(args.data_dir.joinpath("txs").glob("*.json.gz"))
    txs_files = txs_files[:args.limit] if args.limit else txs_files
    jobs = args.jobs or jobs_from_load()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    # t8n runs inside a temporary folder: the binary needs an absolute path
    args.t8n = str(Path(args.t8n).resolve()) if "/" in args.t8n else (shutil.which(args.t8n) or args.t8n)
    print(f"{len(txs_files)} contracts, {jobs} jobs, engine {args.engine} ({args.t8n}), uniform fork {args.fork}",
          flush=True)
    rows: List[Dict] = []
    with ProcessPoolExecutor(max_workers=jobs) as executor:
        # geth recovers the sender from the signature, which a raised gas limit invalidates
        raise_gas_limit = args.engine == "evmone" and not args.original_gas_limit
        futures = [executor.submit(replay_contract, txs_file, args.data_dir, args.variants, args.t8n, args.engine,
                                   args.fork, raise_gas_limit, variants_dir(args)) for txs_file in txs_files]
        for index, future in enumerate(futures, 1):
            rows.extend(future.result())
            if index % 50 == 0 or index == len(futures):
                print(f"{index} / {len(futures)} contracts, {len(rows)} executions", flush=True)
                pd.DataFrame(rows).to_csv(args.out_dir.joinpath("transactions.csv.gz"), index=False)
    args.out_dir.joinpath("settings.json").write_text(json.dumps(
        {"variants": args.variants, "fork": args.fork, "engine": args.engine, "t8n": args.t8n,
         "gas_limit": "block" if raise_gas_limit else "original"}))
    stage_report(argparse.Namespace(out_dir=args.out_dir, data_dir=args.data_dir))


# ---------------------------------------------------------------- fetch-blockhashes

def blockhash_queries(t8n: str, alloc: Dict, env: Dict, transaction: Dict, fork: str, folder: Path) -> set:
    """
    Numbers of the blocks read with BLOCKHASH by an execution (from its EIP-3155 trace: the argument is on top of
    the stack), other than the parent (whose hash is in the header)
    """
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    for name, content in [("alloc.json", alloc), ("env.json", env), ("txs.json", [transaction])]:
        folder.joinpath(name).write_text(json.dumps(content))
    subprocess.run([t8n, "t8n", "--input.alloc", "alloc.json", "--input.env", "env.json", "--input.txs", "txs.json",
                    "--output.basedir", ".", "--output.result", "result.json", "--output.alloc", "post.json",
                    "--state.fork", fork, "--state.chainid", "1", "--state.reward", "0", "--trace"],
                   capture_output=True, text=True, cwd=folder, timeout=600)
    numbers = set()
    for trace in folder.glob("trace-*.jsonl"):
        for line in trace.read_text().splitlines():
            if '"BLOCKHASH"' in line:
                step = json.loads(line)
                if step.get("stack"):
                    numbers.add(int(step["stack"][-1], 16))
    return numbers


def fetch_contract_blockhashes(txs_file: Path, data_dir: Path, hashes: Optional[set], t8n: str, rpc_url: str) \
        -> Tuple[int, int]:
    """
    For the transactions of a contract (those in hashes, or all), the hashes of the blocks older than the parent
    that the original reads with BLOCKHASH, in its receipt replay (own fork and gas limit), stored in its entry as
    block_hashes. The blocks read may depend on the hashes (e.g. a loop until a condition), so the execution is
    repeated with the fetched hashes until no new block is read. Returns (transactions updated, blocks fetched)
    """
    stored = read_json_gz(txs_file)
    codes = CodeStore(data_dir.joinpath("codes"))
    rpc = JsonRpc(rpc_url)
    updated = fetched = 0
    with tempfile.TemporaryDirectory(prefix="gas_blockhash_") as work:
        for data in stored.get("prestate_data") or []:
            if hashes is not None and data["transaction"]["hash"] not in hashes:
                continue
            block = data["block"]
            number = int(block["number"], 16)
            block_hashes = dict(data.get("block_hashes") or {})
            for _ in range(4):
                read = blockhash_queries(t8n, alloc_from_prestate(data["prestate"], codes, None),
                                         environment(block, fork_of(block), block_hashes),
                                         signed_transaction(data["transaction"]), fork_of(block), Path(work, "trace"))
                # BLOCKHASH answers only for the 256 previous blocks (0 otherwise); the parent is in the header
                missing = sorted(n for n in read if number - 256 <= n < number - 1 and str(n) not in block_hashes)
                if not missing:
                    break
                for block_number in missing:
                    block_hashes[str(block_number)] = rpc("eth_getBlockByNumber", hex(block_number), False)["hash"]
                    fetched += 1
            if block_hashes != (data.get("block_hashes") or {}):
                data["block_hashes"] = block_hashes
                updated += 1
    if updated:
        write_json_gz(txs_file, stored)
    return updated, fetched


def stage_fetch_blockhashes(args) -> None:
    """
    By default only the transactions whose receipt replay was invalid in a previous replay (--replay-dir): a made-up
    BLOCKHASH answer can only change the comparison through the receipt check, as the original and the variants
    read the same one
    """
    rpc_url = args.rpc_file.read_text().strip() if args.rpc_file else args.rpc
    t8n = str(Path(args.t8n).resolve()) if "/" in args.t8n else (shutil.which(args.t8n) or args.t8n)
    selected: Optional[Dict[str, set]] = None
    if args.replay_dir:
        executions = pd.read_csv(args.replay_dir.joinpath("transactions.csv.gz"))
        invalid = executions[(executions.variant == "receipt") & (executions.valid != True)]
        selected = {address: set(rows.hash) for address, rows in invalid.groupby("address")}
    txs_files = sorted(args.data_dir.joinpath("txs").glob("*.json.gz"))
    if selected is not None:
        txs_files = [path for path in txs_files if path.name.split(".")[0] in selected]
    with ProcessPoolExecutor(max_workers=args.jobs or 4) as executor:
        futures = {path.name.split(".")[0]: executor.submit(
            fetch_contract_blockhashes, path, args.data_dir,
            selected.get(path.name.split(".")[0]) if selected is not None else None, t8n, rpc_url)
            for path in txs_files}
        for address, future in futures.items():
            updated, fetched = future.result()
            if updated:
                print(f"{address}: {updated} transactions, {fetched} block hashes", flush=True)


# ---------------------------------------------------------------- report

def bucket_weights(data_dir: Path) -> Dict[Tuple[str, str], float]:
    """
    Weight of each sampled transaction of a bucket: transactions of the bucket in the period / transactions sampled
    """
    weights = {}
    for txs_file in data_dir.joinpath("txs").glob("*.json.gz"):
        stored = read_json_gz(txs_file)
        sampled = pd.Series([entry.get("bucket") for entry in stored["selected"]]).value_counts()
        for bucket, count in sampled.items():
            total = (stored.get("buckets") or {}).get(bucket, {}).get("transactions", count)
            weights[(stored["address"], bucket)] = total / count
    return weights


EXECUTION_COLUMNS = ["address", "hash", "bucket", "block", "own_fork", "variant", "fork", "status", "gas_used",
                     "receipt_gas_used", "valid", "status_match", "logs_match", "state_match", "matches_original",
                     "error"]


def stage_report(args) -> None:
    settings = json.loads(args.out_dir.joinpath("settings.json").read_text())
    variants = settings["variants"]
    executions = pd.read_csv(args.out_dir.joinpath("transactions.csv.gz")).reindex(columns=EXECUTION_COLUMNS)
    executions["error"] = executions["error"].fillna("")
    lines = [f"Offline replay ({settings['engine']}, uniform fork {settings['fork']}, gas limit "
             f"{settings.get('gas_limit', 'original')}): "
             f"{executions.address.nunique()} contracts, {executions.hash.nunique()} transactions"]
    receipt = executions[executions.variant == "receipt"]
    lines.append(f"  receipt check (own fork): {int((receipt.valid == True).sum())} valid of "
                 f"{len(receipt)}; errors {dict(receipt[receipt.error != ''].error.str[:70].value_counts().head(5))}")
    valid_hashes = set(receipt[(receipt.valid == True)].hash)
    complete = executions[executions.hash.isin(valid_hashes) & executions.variant.isin(["original"] + variants)]
    for variant in variants:
        rows = complete[complete.variant == variant]
        lines.append(f"  {variant}: errors {dict(rows[rows.error != ''].error.str[:70].value_counts().head(5))}, "
                     f"mismatches with the original {int((rows.matches_original == False).sum())} "
                     f"(status {int((rows.status_match == False).sum())}, logs {int((rows.logs_match == False).sum())}, "
                     f"state {int((rows.state_match == False).sum())})")
    good = complete[complete.error == ""]
    matching = good[good.variant.isin(variants)].groupby("hash").matches_original.agg(
        lambda values: all(value is True for value in values) and len(values) == len(variants))
    compared = set(matching[matching].index) & set(good[good.variant == "original"].hash)
    pivot = good[good.hash.isin(compared)].pivot_table(index=["address", "bucket", "hash"], columns="variant",
                                                       values="gas_used", aggfunc="first")
    if len(pivot) == 0 or not set(["original"] + variants) <= set(pivot.columns):
        lines.append("\nno transaction is valid and matching for every variant")
        summary = "\n".join(lines)
        args.out_dir.joinpath("summary.txt").write_text(summary + "\n")
        print(summary)
        return
    weights = bucket_weights(args.data_dir)
    pivot["weight"] = [weights.get((address, bucket), 1.0) for address, bucket, _ in pivot.index]
    lines.append(f"\nover {len(pivot)} transactions valid and matching for every variant "
                 f"({pivot.index.get_level_values('address').nunique()} contracts):")
    reference = variants[0]
    for variant in ["original"] + variants:
        if variant == reference:
            continue
        difference = pivot[variant] - pivot[reference]
        plain = difference.sum() / pivot[reference].sum()
        weighted = (difference * pivot.weight).sum() / (pivot[reference] * pivot.weight).sum()
        lines.append(f"  {variant} vs {reference}: plain {int(difference.sum()):+,} gas ({100 * plain:+.3f}%), "
                     f"weighted by frequency {100 * weighted:+.3f}%; better / worse / equal "
                     f"{(difference < 0).sum()} / {(difference > 0).sum()} / {(difference == 0).sum()}")
    summary = "\n".join(lines)
    args.out_dir.joinpath("summary.txt").write_text(summary + "\n")
    print(summary)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="stage", required=True)

    codes_parser = subparsers.add_parser("codes")
    codes_parser.add_argument("data_dir", type=Path)
    codes_parser.add_argument("results_dir", type=Path, help="Output folder of compare_variants.py --keep-artifacts")
    codes_parser.add_argument("--inputs-from", type=Path, dest="inputs_from", required=True)
    codes_parser.add_argument("--solc", type=Path, required=True)
    codes_parser.add_argument("--variant", dest="variants", action="append", required=True,
                              type=lambda value: tuple(value.split("=", 1)), help="NAME=ARTIFACT_FOLDER")
    codes_parser.add_argument("--depth", type=int, default=16)
    codes_parser.add_argument("--jobs", type=int, default=None)
    codes_parser.add_argument("--variants-dir", type=Path, dest="variants_dir", default=None,
                              help="Where the runtime codes are written (default <data_dir>/variants)")

    replay_parser = subparsers.add_parser("replay")
    replay_parser.add_argument("data_dir", type=Path)
    replay_parser.add_argument("--variants", type=lambda value: value.split(","), required=True,
                               help="Comma-separated names given to the codes stage; the first is the reference")
    replay_parser.add_argument("--t8n", required=True, help="evmone CLI binary (evaluation/scripts/install_evmone.sh), or "
                                                             "geth's evm with --engine geth")
    replay_parser.add_argument("--engine", choices=["evmone", "geth"], default="evmone")
    replay_parser.add_argument("--fork", default="Prague", help="Fork of the uniform replay")
    replay_parser.add_argument("--original-gas-limit", action="store_true", dest="original_gas_limit",
                               help="Uniform executions with the transaction's own gas limit (always with geth)")
    replay_parser.add_argument("--out-dir", type=Path, dest="out_dir", required=True)
    replay_parser.add_argument("--jobs", type=int, default=None)
    replay_parser.add_argument("--variants-dir", type=Path, dest="variants_dir", default=None,
                               help="Where the runtime codes are read (default <data_dir>/variants)")
    replay_parser.add_argument("--limit", type=int, default=None)

    report_parser = subparsers.add_parser("report")
    report_parser.add_argument("out_dir", type=Path)
    report_parser.add_argument("data_dir", type=Path)

    blockhash_parser = subparsers.add_parser("fetch-blockhashes")
    blockhash_parser.add_argument("data_dir", type=Path)
    blockhash_parser.add_argument("--replay-dir", type=Path, dest="replay_dir", default=None,
                                  help="Only the transactions whose receipt check was invalid in this replay")
    blockhash_parser.add_argument("--t8n", default="evm", help="A t8n tool with --trace (geth's evm, or evmone)")
    blockhash_parser.add_argument("--rpc", default="https://eth.drpc.org")
    blockhash_parser.add_argument("--rpc-file", type=Path, dest="rpc_file", default=None)
    blockhash_parser.add_argument("--jobs", type=int, default=None)

    resolve_parser = subparsers.add_parser("resolve-etherscan")
    resolve_parser.add_argument("data_dir", type=Path)
    resolve_parser.add_argument("--solc-cache", type=Path, dest="solc_cache",
                                default=Path.home().joinpath(".cache", "grey", "solc"),
                                help="Where missing official solc binaries are downloaded")

    immutables_parser = subparsers.add_parser("resolve-immutables")
    immutables_parser.add_argument("data_dir", type=Path)
    immutables_parser.add_argument("--solc", type=Path, required=True,
                                   help="The compiler of the variants (numbers the declarations of the corpus inputs)")
    immutables_parser.add_argument("--corpus-dir", type=Path, dest="corpus_dir",
                                   default=CORPUS_FOLDER)
    immutables_parser.add_argument("--solc-cache", type=Path, dest="solc_cache",
                                   default=Path.home().joinpath(".cache", "grey", "solc"))
    immutables_parser.add_argument("--jobs", type=int, default=None)

    args = parser.parse_args()
    {"resolve-immutables": stage_resolve_immutables, "codes": stage_codes, "replay": stage_replay, "report": stage_report,
     "resolve-etherscan": stage_resolve_etherscan, "fetch-blockhashes": stage_fetch_blockhashes}[args.stage](args)


if __name__ == "__main__":
    main()
