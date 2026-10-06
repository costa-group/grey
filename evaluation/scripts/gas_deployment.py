#!/usr/bin/env python3
"""
Deployment gas of the most-called contracts with each variant's creation code, measured on the real creation of each
contract (evaluation/scripts/run_mainnet_gas_evaluation.sh does the same for the calls).

Stages:
  fetch <data_dir> [--rpc URL] [--jobs N]            (local, RPC with archive state and debug_traceTransaction)
      For the creation transaction of each contract (deploy/<address>.json.gz): the transaction, its receipt, the
      header of its block, its prestate and the post state of the contract (prestateTracer, also in diff mode), and
      the frame that created the contract (callTracer): CREATE or CREATE2, sender, value and creation input. Writes
      <data_dir>/deploy_txs/<address>.json.gz (codes in <data_dir>/codes, as the other prestates).
  replay <data_dir> --mc-dir DIR --t8n BINARY --out FILE [--jobs N]     (work machine, evmone t8n)
      Per contract, the creation executed with the original creation input and with solc's and grey's creation code
      (from a folder of run_experiments_most_called_*.sh: <address>.output and <address>.log) plus the real
      constructor arguments, under Prague (the same rules for all), from the prestate of the creation transaction:
        - contracts deployed by an account: the real transaction with its input replaced;
        - contracts created by another contract (a factory): a direct creation sent by the factory's address, whose
          code is removed from the prestate (a transaction cannot come from an account with code). msg.sender is
          the factory as in the real creation; tx.origin and the address of the contract change.
      The original creation must reproduce the deployed code and the storage of the contract (validation); the
      variants must succeed and leave the same storage. The gas is the transaction's gasUsed without the intrinsic
      gas (21000/53000, calldata, EIP-3860 initcode words, access list): code deposit (200 per byte) plus the
      constructor's execution, minus its refund.
  report <file> [<file> ...]
      Totals over the contracts valid for every variant.
"""
import argparse
import gzip
import json
import re
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gas_mainnet_replay import JsonRpc, read_json_gz, store_code, write_json_gz   # noqa: E402

# ---------------------------------------------------------------- keccak256 (no dependencies)

_ROUND_CONSTANTS = [
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000, 0x000000000000808B,
    0x0000000080000001, 0x8000000080008081, 0x8000000000008009, 0x000000000000008A, 0x0000000000000088,
    0x0000000080008009, 0x000000008000000A, 0x000000008000808B, 0x800000000000008B, 0x8000000000008089,
    0x8000000000008003, 0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
    0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008]
_ROTATIONS = [[0, 36, 3, 41, 18], [1, 44, 10, 45, 2], [62, 6, 43, 15, 61], [28, 55, 25, 21, 56], [27, 20, 39, 8, 14]]
_MASK = (1 << 64) - 1


def _keccak_f(state):
    for round_constant in _ROUND_CONSTANTS:
        c = [state[x][0] ^ state[x][1] ^ state[x][2] ^ state[x][3] ^ state[x][4] for x in range(5)]
        d = [c[(x - 1) % 5] ^ (((c[(x + 1) % 5] << 1) | (c[(x + 1) % 5] >> 63)) & _MASK) for x in range(5)]
        state = [[state[x][y] ^ d[x] for y in range(5)] for x in range(5)]
        b = [[0] * 5 for _ in range(5)]
        for x in range(5):
            for y in range(5):
                r = _ROTATIONS[x][y]
                b[y][(2 * x + 3 * y) % 5] = ((state[x][y] << r) | (state[x][y] >> (64 - r))) & _MASK if r else state[x][y]
        state = [[b[x][y] ^ ((~b[(x + 1) % 5][y]) & b[(x + 2) % 5][y]) for y in range(5)] for x in range(5)]
        state[0][0] ^= round_constant
    return state


def keccak256(data: bytes) -> bytes:
    rate = 136
    padded = bytearray(data) + b"\x01" + b"\x00" * ((rate - (len(data) + 1) % rate) % rate)
    padded[-1] |= 0x80
    state = [[0] * 5 for _ in range(5)]
    for start in range(0, len(padded), rate):
        block = padded[start:start + rate]
        for i in range(rate // 8):
            state[i % 5][i // 5] ^= int.from_bytes(block[8 * i:8 * i + 8], "little")
        state = _keccak_f(state)
    return b"".join(state[i % 5][i // 5].to_bytes(8, "little") for i in range(4))


def create_address(sender: str, nonce: int) -> str:
    """Address of a contract created with CREATE: keccak256(rlp([sender, nonce]))[12:]"""
    if nonce == 0:
        encoded_nonce = b"\x80"
    elif nonce < 0x80:
        encoded_nonce = bytes([nonce])
    else:
        raw = nonce.to_bytes((nonce.bit_length() + 7) // 8, "big")
        encoded_nonce = bytes([0x80 + len(raw)]) + raw
    payload = b"\x94" + bytes.fromhex(sender[2:]) + encoded_nonce
    return "0x" + keccak256(bytes([0xc0 + len(payload)]) + payload)[12:].hex()


def create2_address(sender: str, salt: bytes, initcode_hash: bytes) -> str:
    return "0x" + keccak256(b"\xff" + bytes.fromhex(sender[2:]) + salt + initcode_hash)[12:].hex()


# Code put at the factory's address to create the contract from the transaction's input (32-byte salt, then the
# creation input): CALLDATACOPY of the creation input to memory 0, then CREATE (value, 0, size) or CREATE2 (value, 0,
# size, salt), STOP. The constructor sees msg.sender = the factory and tx.origin = the real sender
LAUNCHER_CREATE = "602036038060205f375f34f000"
LAUNCHER_CREATE2 = "602036038060205f375f35905f34f500"
DUMMY_LIBRARY = "00000000000000000000000000000000000000aa"


# ---------------------------------------------------------------- fetch

def find_creation_frame(frame: Dict, address: str) -> Optional[Dict]:
    if frame.get("type") in ("CREATE", "CREATE2") and (frame.get("to") or "").lower() == address:
        return frame
    for child in frame.get("calls") or []:
        found = find_creation_frame(child, address)
        if found is not None:
            return found
    return None


def fetch_contract(address: str, data_dir: Path, rpc_url: str) -> str:
    target = data_dir / "deploy_txs" / f"{address}.json.gz"
    if target.is_file():
        return "kept"
    deploy = read_json_gz(data_dir / "deploy" / f"{address}.json.gz")
    transaction_hash = deploy.get("creation_transaction")
    if not transaction_hash:
        return "no creation transaction"
    rpc = JsonRpc(rpc_url)
    codes_dir = data_dir / "codes"
    transaction = rpc("eth_getTransactionByHash", transaction_hash)
    receipt = rpc("eth_getTransactionReceipt", transaction_hash)
    receipt.pop("logsBloom", None)
    block = rpc("eth_getBlockByNumber", transaction["blockNumber"], False)
    block.pop("transactions", None)
    block.pop("logsBloom", None)
    prestate = rpc("debug_traceTransaction", transaction_hash, {"tracer": "prestateTracer", "timeout": "120s"})
    diff = rpc("debug_traceTransaction", transaction_hash,
               {"tracer": "prestateTracer", "tracerConfig": {"diffMode": True}, "timeout": "120s"})
    calls = rpc("debug_traceTransaction", transaction_hash, {"tracer": "callTracer", "timeout": "120s"})
    frame = find_creation_frame(calls, address)
    if frame is None:
        return "no creation frame for the contract in the creation transaction"
    for account in prestate.values():
        if account.get("code") not in (None, "0x"):
            account["code"] = store_code(codes_dir, account["code"])
    post = diff.get("post", {}).get(address, {})
    write_json_gz(target, {
        "address": address, "transaction": transaction, "receipt": receipt, "block": block, "prestate": prestate,
        "post_code": store_code(codes_dir, post.get("code", "0x")), "post_storage": post.get("storage") or {},
        "frame": {"type": frame["type"], "from": frame["from"].lower(), "value": frame.get("value", "0x0"),
                  "input": store_code(codes_dir, frame["input"]), "gas_used": frame.get("gasUsed"),
                  "error": frame.get("error")}})
    return "fetched"


def stage_fetch(args) -> None:
    addresses = sorted(path.name.split(".")[0] for path in args.data_dir.joinpath("deploy").glob("*.json.gz"))
    args.data_dir.joinpath("deploy_txs").mkdir(exist_ok=True)

    def fetch(address):
        for attempt in range(3):
            try:
                return address, fetch_contract(address, args.data_dir, args.rpc)
            except Exception as exception:
                error = f"{type(exception).__name__}: {str(exception)[:150]}"
                time.sleep(5 * (attempt + 1))
        return address, error

    outcomes = {}
    with ThreadPoolExecutor(args.jobs) as executor:
        for done, (address, outcome) in enumerate(executor.map(fetch, addresses), 1):
            outcomes[address] = outcome
            if done % 50 == 0:
                print(f"{done} / {len(addresses)}", flush=True)
    summary = {}
    for outcome in outcomes.values():
        summary[outcome[:80]] = summary.get(outcome[:80], 0) + 1
    print(json.dumps(summary, indent=1))


# ---------------------------------------------------------------- replay

PLACEHOLDER = re.compile(r"__\$[0-9a-fA-F]{34}\$__")


def creation_codes(address: str, mc_dir: Path, deploy: Dict) -> Dict:
    """Creation code of the deployed contract per variant (solc: <address>.output; grey: <address>.log)"""
    folder = mc_dir / address
    contract, source = deploy.get("contract"), deploy.get("source")
    output = json.loads((folder / f"{address}.output").read_text())
    candidates = [(file, contracts[contract]) for file, contracts in (output.get("contracts") or {}).items()
                  if contract in contracts and contracts[contract].get("evm", {}).get("bytecode", {}).get("object")]
    codes = {}
    if candidates:
        file, info = candidates[0]
        codes["solc"] = info["evm"]["bytecode"]["object"]
        codes["link_references"] = info["evm"]["bytecode"].get("linkReferences") or {}
        codes["source_file"] = file
    for line in (folder / f"{address}.log").read_text(errors="replace").splitlines():
        if line.startswith("Contract: ") and "-> EVM Code:" in line:
            name = line.split("->")[0].split(":")[-1].strip()
            if name == contract:
                codes["grey"] = line.split("->")[-1].split(":")[-1].strip()
    return codes


def link(code: str, solc_code: str, link_references: Dict, libraries: Dict[str, str]) -> Optional[str]:
    """Links the library placeholders: their positions come from solc's link references (the same placeholder text
    in grey's code), the addresses from the input's settings.libraries or Etherscan"""
    if "__$" not in code:
        return code
    placeholders = {}
    for file, file_libraries in link_references.items():
        for library, references in file_libraries.items():
            start = references[0]["start"] * 2
            address = libraries.get(f"{file}:{library}") or libraries.get(library)
            if address is None:
                continue
            placeholders[solc_code[start:start + 40]] = address.lower().removeprefix("0x").rjust(40, "0")
    # Libraries without a known address (e.g. a reference that solc's optimizer removes and grey keeps): a dummy
    # address, which only matters if the constructor calls the library
    return PLACEHOLDER.sub(lambda match: placeholders.get(match.group(0), DUMMY_LIBRARY), code)


# Words of the deployed code that may differ when the contract is deployed at another address (immutables computed
# from address(this))
MAX_ADDRESS_DEPENDENT_WORDS = 4


def differing_words(code: str, expected: str) -> Optional[int]:
    """Number of 32-byte words (aligned to the start of the code) that differ, or None if the sizes differ"""
    if len(code) != len(expected):
        return None
    return len({position // 64 for position in range(0, len(code), 2) if code[position:position + 2] !=
                expected[position:position + 2]})


def run_t8n_traced(t8n: str, alloc: Dict, env: Dict, transaction: Dict, folder: Path) -> Dict:
    """One transaction through evmone t8n under Prague, with the execution trace (trace-*.jsonl in folder)"""
    import shutil
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    for name, content in [("alloc.json", alloc), ("env.json", env), ("txs.json", [transaction])]:
        folder.joinpath(name).write_text(json.dumps(content))
    completed = subprocess.run([t8n, "t8n", "--input.alloc", "alloc.json", "--input.env", "env.json", "--input.txs",
                                "txs.json", "--output.basedir", ".", "--output.result", "result.json", "--output.alloc",
                                "post.json", "--state.fork", "Prague", "--state.chainid", "1", "--state.reward", "0",
                                "--trace"], capture_output=True, text=True, cwd=folder, timeout=600)
    result_file = folder / "result.json"
    if completed.returncode != 0 or not result_file.is_file():
        return {"error": f"t8n failed: {(completed.stderr or completed.stdout).strip()[-200:]}"}
    result = json.loads(result_file.read_text())
    if result.get("rejected"):
        return {"error": f"rejected: {str(result['rejected'][0].get('error'))[:150]}"}
    receipt = result["receipts"][0]
    traces = list(folder.glob("trace-*.jsonl"))
    return {"status": int(receipt["status"], 16), "gas_used": int(receipt["gasUsed"], 16),
            "post": json.loads((folder / "post.json").read_text()), "trace": traces[0] if traces else None, "error": ""}


def create_step(trace_file: Path) -> List[Dict]:
    """The CREATE/CREATE2 executed in a trace: depth, opcode, the gas of its constructor (gas at the first step of the
    new frame minus the gas left after its last step) and the size of the code it returns. The order of the list is
    the order of execution"""
    creates, open_creates = [], []   # open_creates: (index in creates, depth of the CREATE)
    last = {}                         # depth -> last step seen
    with open(trace_file) as f:
        for line in f:
            if '"opName"' not in line:
                continue
            step = json.loads(line)
            depth = step["depth"]
            # Frames that have ended: close the CREATEs whose constructor frame (depth + 1) has finished
            while open_creates and depth <= open_creates[-1][1]:
                index, create_depth = open_creates.pop()
                child_last = last.get(create_depth + 1)
                if child_last is not None and creates[index]["first_gas"] is not None:
                    creates[index]["constructor_gas"] = creates[index]["first_gas"] - \
                        (int(child_last["gas"], 16) - int(child_last.get("gasCost", "0x0"), 16))
                    stack = child_last.get("stack") or []
                    creates[index]["returned_size"] = int(stack[-2], 16) if child_last["opName"] == "RETURN" and \
                        len(stack) >= 2 else 0
                last.pop(create_depth + 1, None)
            if open_creates and depth == open_creates[-1][1] + 1 and creates[open_creates[-1][0]]["first_gas"] is None:
                creates[open_creates[-1][0]]["first_gas"] = int(step["gas"], 16)
            last[depth] = step
            if step["opName"] in ("CREATE", "CREATE2"):
                creates.append({"depth": depth, "op": step["opName"], "first_gas": None, "constructor_gas": None,
                                "returned_size": 0})
                open_creates.append((len(creates) - 1, depth))
    for index, create in enumerate(creates):
        create["key"] = (create["depth"], create["op"],
                         sum(1 for c in creates[:index] if (c["depth"], c["op"]) == (create["depth"], create["op"])))
    return creates


def patched_transaction_input(transaction_input: str, original: str, replacement: str) -> Optional[str]:
    """The transaction's input with the creation input replaced, when the factory takes it from the transaction:
    as the last ABI 'bytes' argument (its length word before it, zero padding to the end) or raw at the end"""
    data, old = transaction_input[2:].lower(), original[2:].lower()
    position = data.rfind(old)
    if position < 0 or position % 2:
        return None
    length_word = data[position - 64:position] if position >= 64 else ""
    tail = data[position + len(old):]
    new = replacement[2:].lower()
    if length_word and int(length_word, 16) == len(old) // 2 and set(tail) <= {"0"} and len(tail) < 64:
        padding = "0" * ((64 - len(new) % 64) % 64)
        return "0x" + data[:position - 64] + format(len(new) // 2, "064x") + new + padding
    if not tail:
        return "0x" + data[:position] + new
    return None


def intrinsic_creation_gas(data: bytes, access_list: List[Dict]) -> int:
    zero_bytes = data.count(0)
    gas = 53000 + 4 * zero_bytes + 16 * (len(data) - zero_bytes) + 2 * ((len(data) + 31) // 32)
    for entry in access_list or []:
        gas += 2400 + 1900 * len(entry.get("storageKeys") or [])
    return gas


def replay_contract(address: str, data_dir: Path, mc_dir: Path, t8n: str) -> Dict:
    import gas_offline_replay as g
    stored_file = data_dir / "deploy_txs" / f"{address}.json.gz"
    if not stored_file.is_file():
        return {"address": address, "error": "no creation data"}
    stored = read_json_gz(stored_file)
    deploy = read_json_gz(data_dir / "deploy" / f"{address}.json.gz")
    codes_store = g.CodeStore(data_dir / "codes")
    frame = stored["frame"]
    original_input = codes_store.get(frame["input"])
    arguments = (deploy.get("constructor_arguments") or "0x")[2:]
    result = {"address": address, "contract": deploy.get("contract"), "factory": bool(deploy.get("factory")),
              "frame": frame["type"]}
    if frame.get("error"):
        return {**result, "error": f"the real creation failed: {frame['error']}"}
    if arguments and not original_input.endswith(arguments):
        return {**result, "error": "the constructor arguments are not at the end of the real creation input"}
    try:
        codes = creation_codes(address, mc_dir, deploy)
    except Exception as exception:
        return {**result, "error": f"codes: {type(exception).__name__}: {exception}"[:150]}
    libraries = {}
    try:
        input_libraries = json.loads((mc_dir / address / f"{address}_standard_input.json").read_text()) \
            .get("settings", {}).get("libraries") or {}
        for file, names in input_libraries.items():
            for name, library_address in names.items():
                libraries[f"{file}:{name}"] = libraries[name] = library_address
        libraries.update(g.etherscan_libraries(address).get("", {}))
    except Exception:
        pass
    inputs = {"original": original_input}
    for variant in ("solc", "grey"):
        if variant not in codes:
            result[f"{variant}_error"] = "no code"
            continue
        linked = link(codes[variant], codes.get("solc", ""), codes.get("link_references", {}), libraries)
        result[f"{variant}_dummy_library"] = DUMMY_LIBRARY in linked
        inputs[variant] = "0x" + linked + arguments

    transaction, block = stored["transaction"], stored["block"]
    base = g.signed_transaction(transaction)
    base.pop("hash", None)
    prestate = {account: dict(info) for account, info in stored["prestate"].items()}
    # A direct deployment only if the contract is the transaction's own creation; otherwise its creator (a factory, or
    # a contract created by the same transaction) creates it
    factory = None if (not transaction.get("to") and frame["from"] == transaction["from"].lower()) else frame["from"]
    launcher, salt, method = None, b"", "real transaction" if not factory else None
    real_prestate = {account: dict(info) for account, info in prestate.items()}
    if factory and transaction.get("to") and \
            patched_transaction_input(transaction.get("input") or "0x", original_input, original_input):
        # The factory takes the creation input from the transaction: the real transaction with it replaced (the
        # factory's own code runs, with its callbacks)
        method = "factory, creation input in the transaction"
    elif factory:
        # A launcher at the factory's address creates the contract from the transaction's input: msg.sender is the
        # factory and tx.origin the real sender, but the factory's own code does not run (callbacks to it fail)
        method = "factory replaced by a launcher"
        account = prestate.setdefault(factory, {"balance": "0x0"})
        if frame["type"] == "CREATE2":
            initcode_hash = keccak256(bytes.fromhex(original_input[2:]))
            data = bytes.fromhex((transaction.get("input") or "0x")[2:])
            candidates = {data[i:i + 32] for i in range(0, max(len(data) - 31, 0))}
            salt = next((c for c in candidates if create2_address(factory, c, initcode_hash) == address), None)
            result["salt_found"] = salt is not None
            salt = salt or bytes(32)
            launcher = LAUNCHER_CREATE2
        else:
            # The factory's nonce that gives the real address (earlier creations of the same transaction count)
            nonce = int(account.get("nonce", 0)) if not isinstance(account.get("nonce"), str) else int(account["nonce"], 16)
            nonce = next((n for n in range(nonce, nonce + 256) if create_address(factory, n) == address), nonce)
            account["nonce"] = nonce
            launcher = LAUNCHER_CREATE
        account["code"] = "0x" + launcher
        base.update(to=factory, value=frame["value"])
        if not transaction.get("to"):
            # The creator is created by the same transaction: the transaction calls it instead
            base["nonce"] = transaction["nonce"]
    result["method"] = method
    base["gas"] = block["gasLimit"]
    # The sender pays for the block's gas limit
    price = int(base.get("maxFeePerGas") or base.get("gasPrice") or "0x0", 16)
    sender_account = prestate.setdefault(base["sender"].lower(), {"balance": "0x0"})
    sender_account["balance"] = hex(int(sender_account.get("balance", "0x0"), 16) + int(block["gasLimit"], 16) * price
                                    + int(base.get("value", "0x0"), 16))
    expected_code = codes_store.get(stored["post_code"])
    expected_storage = {key: value for key, value in stored["post_storage"].items() if int(value, 16) != 0}
    result["created_code_bytes"] = len(expected_code) // 2 - 1
    alloc = g.alloc_from_prestate(prestate, codes_store, None)
    environment = g.environment(block, "Prague", None)

    target_key = {}

    def execute(name, creation_input, work):
        """Runs the creation with a creation input; returns the outcome, the created address and the gas that is not
        the deployment (deposit + constructor)"""
        words = (len(creation_input) // 2 - 1 + 31) // 32
        if not factory:
            data = creation_input
            outcome = g.run_t8n(t8n, "evmone", alloc, environment, dict(base, input=data), "Prague", Path(work, name))
            return outcome, address, intrinsic_creation_gas(bytes.fromhex(data[2:]), base.get("accessList"))
        if launcher:
            data = "0x" + salt.hex() + creation_input[2:]
        else:
            data = patched_transaction_input(transaction["input"], original_input, creation_input)
        outcome = run_t8n_traced(t8n, alloc, environment, dict(base, input=data), Path(work, name))
        if outcome.get("error") or not outcome.get("trace"):
            return outcome, None, 0
        # The deployment is the constructor executed by the CREATE/CREATE2 that creates the contract plus its code
        # deposit (200 per byte returned). The original: the creation that returns the real code's size; the
        # variants: the creation at the same place (depth, opcode and order)
        creates = [c for c in create_step(outcome["trace"]) if c["constructor_gas"] is not None]
        if name == "original":
            step = next((c for c in creates if c["returned_size"] == len(expected_code) // 2 - 1), None)
            if step is None:
                return {**outcome, "status": 0}, None, 0
            target_key["key"] = step["key"]
        else:
            step = next((c for c in creates if c["key"] == target_key.get("key")), None)
            if step is None:
                return {**outcome, "status": 0}, None, 0
        deployment = step["constructor_gas"] + 200 * step["returned_size"]
        # The created address: the new account with the returned code
        post = {key.lower(): value for key, value in outcome["post"].items()}
        # (the prestate may already list the address, as an empty account)
        code_before = {a.lower(): info.get("code", "0x") for a, info in alloc.items()}
        new = [account for account, info in post.items() if code_before.get(account, "0x") in ("0x", "")
               and len(info.get("code", "0x")) // 2 - 1 == step["returned_size"] and step["returned_size"] > 0]
        created = address if address in new else (new[0] if new else None)
        return outcome, created, outcome["gas_used"] - deployment

    with tempfile.TemporaryDirectory(prefix="deploy_") as work:
        original_storage = None
        for variant, creation_input in inputs.items():
            outcome, created, intrinsic = execute(variant, creation_input, work)
            if outcome.get("error"):
                result[f"{variant}_error"] = outcome["error"][:150]
                continue
            account = {key.lower(): value for key, value in outcome["post"].items()}.get(created, {})
            code = account.get("code", "0x")
            storage = {key: value for key, value in (account.get("storage") or {}).items() if int(value, 16) != 0}
            deposit = 200 * (len(code) // 2 - 1) if outcome["status"] == 1 and len(code) > 2 else 0
            result.update({f"{variant}_status": int(outcome["status"] == 1 and len(code) > 2),
                           f"{variant}_gas_used": outcome["gas_used"],
                           f"{variant}_intrinsic": intrinsic, f"{variant}_deposit": deposit,
                           f"{variant}_constructor": outcome["gas_used"] - intrinsic - deposit,
                           f"{variant}_code_bytes": len(code) // 2 - 1,
                           # The variants' storage is compared with the one the original creation leaves here (the
                           # real post state may include what the transaction did after the creation, e.g. an
                           # initialize() call of the factory)
                           f"{variant}_storage_matches": storage == (expected_storage if variant == "original"
                                                                     else original_storage)})
            if variant == "original":
                original_storage = storage
                result["original_code_identical"] = code.lower() == expected_code.lower()
                result["original_address_identical"] = created == address
                # At another address (CREATE2 without the real salt), the immutables computed from address(this)
                # (e.g. an EIP-712 domain separator) change, and nothing else may
                different_words = differing_words(code.lower(), expected_code.lower())
                result["original_differing_words"] = different_words
                result["valid"] = result["original_status"] == 1 and \
                    (result["original_code_identical"] or (created != address and different_words is not None
                                                           and different_words <= MAX_ADDRESS_DEPENDENT_WORDS))
    return result


def stage_replay(args) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    addresses = sorted(path.name.split(".")[0] for path in args.data_dir.joinpath("deploy_txs").glob("*.json.gz"))
    t8n = str(Path(args.t8n).resolve())
    with ProcessPoolExecutor(args.jobs) as executor:
        rows = list(executor.map(replay_contract, addresses, [args.data_dir] * len(addresses),
                                 [args.mc_dir] * len(addresses), [t8n] * len(addresses)))
    args.out.write_text(json.dumps(rows, indent=1))
    report([args.out])


# ---------------------------------------------------------------- report

def report(files: List[Path]) -> None:
    for file in files:
        rows = json.loads(Path(file).read_text())
        valid = [r for r in rows if r.get("valid")]
        good = [r for r in valid if r.get("solc_status") == 1 and r.get("grey_status") == 1
                and r.get("solc_storage_matches") and r.get("grey_storage_matches")]
        print(f"===== {file}: {len(rows)} contracts; the real creation is reproduced in {len(valid)} "
              f"({sum(r['factory'] for r in valid)} created by a factory; "
              f"{sum(not r.get('original_code_identical') for r in valid)} with address-dependent immutables; "
              f"{sum(not r.get('original_storage_matches') for r in valid)} whose transaction changes the contract "
              f"after creating it); "
              f"solc and grey succeed with the same storage in {len(good)}")
        invalid = {}
        for r in rows:
            if not r.get("valid"):
                reason = r.get("error") or r.get("original_error") or (
                    "the original creation fails here (the constructor calls the factory or reads what it stored "
                    "earlier in the transaction)" if r.get("original_status") == 0 else
                    "the original creation deploys another code")
                invalid[reason[:70]] = invalid.get(reason[:70], 0) + 1
        print("  not reproduced:", invalid)
        failing = {}
        for r in valid:
            if r not in good:
                for variant in ("solc", "grey"):
                    reason = r.get(f"{variant}_error") or ("fails" if r.get(f"{variant}_status") != 1 else
                                                          "different storage" if not r.get(f"{variant}_storage_matches")
                                                          else "")
                    if reason:
                        failing[f"{variant}: {reason[:60]}"] = failing.get(f"{variant}: {reason[:60]}", 0) + 1
        print("  excluded (variants):", failing)
        if not good:
            continue
        for label, key in [("gas used", "gas_used"), ("intrinsic and calldata (and the factory launcher)", "intrinsic"),
                           ("code deposit", "deposit"), ("constructor execution", "constructor")]:
            solc, grey = sum(r[f"solc_{key}"] for r in good), sum(r[f"grey_{key}"] for r in good)
            print(f"  {label:45s} solc {solc:>14,}  grey {grey:>14,}  ({100 * (grey - solc) / solc if solc else 0:+.2f}%)")
        solc = sum(r["solc_gas_used"] - r["solc_intrinsic"] for r in good)
        grey = sum(r["grey_gas_used"] - r["grey_intrinsic"] for r in good)
        better = sum(r["grey_gas_used"] - r["grey_intrinsic"] < r["solc_gas_used"] - r["solc_intrinsic"] for r in good)
        worse = sum(r["grey_gas_used"] - r["grey_intrinsic"] > r["solc_gas_used"] - r["solc_intrinsic"] for r in good)
        print(f"  {'WITHOUT intrinsic nor calldata':45s} solc {solc:>14,}  grey {grey:>14,}  "
              f"({100 * (grey - solc) / solc:+.2f}%); grey better / worse / equal {better} / {worse} / "
              f"{len(good) - better - worse}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="stage", required=True)
    fetch_parser = subparsers.add_parser("fetch")
    fetch_parser.add_argument("data_dir", type=Path)
    fetch_parser.add_argument("--rpc", default="https://eth.drpc.org")
    fetch_parser.add_argument("--jobs", type=int, default=8)
    replay_parser = subparsers.add_parser("replay")
    replay_parser.add_argument("data_dir", type=Path)
    replay_parser.add_argument("--mc-dir", type=Path, required=True, dest="mc_dir")
    replay_parser.add_argument("--t8n", required=True)
    replay_parser.add_argument("--out", type=Path, required=True)
    replay_parser.add_argument("--jobs", type=int, default=8)
    report_parser = subparsers.add_parser("report")
    report_parser.add_argument("files", type=Path, nargs="+")
    args = parser.parse_args()
    {"fetch": stage_fetch, "replay": stage_replay, "report": lambda a: report(a.files)}[args.stage](args)


if __name__ == "__main__":
    main()
