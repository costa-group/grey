"""
Base of the reparation's memory slots without a memoryguard: inline assembly that is not memory-safe can use fixed
addresses above the initial free memory pointer, so the slots must start above the largest constant memory access.
"""
import shutil
import subprocess
from pathlib import Path

import pandas as pd
import pytest

from parser.parser import parse_CFG_from_json_dict
from reparation.repair_unreachable import largest_constant_memory_access, spill_base

REPO_ROOT = Path(__file__).resolve().parent.parent
SOLC = REPO_ROOT.joinpath("examples/solc-without-opt")
FIXED_MEMORY_CONTRACT = Path(__file__).resolve().parent.joinpath("files/fixed_memory_assembly.sol")


def object_json(first_instruction, function_instructions):
    """
    An object whose main block starts with the given instruction and calls a function with the given instructions
    """
    main_block = {"id": "Block0", "type": "FunctionCall", "exit": {"type": "Terminated"},
                  "instructions": [first_instruction, {"in": [], "op": "f", "out": []},
                                   {"in": ["0x00", "0x00"], "op": "return", "out": []}],
                  "liveness": {"in": [], "out": []}}
    function = {"arguments": ["v0"], "entry": "Block0", "numReturns": 0, "type": "Function",
                "blocks": [{"id": "Block0", "type": "BuiltinCall", "exit": {"returnValues": [], "type": "FunctionReturn"},
                            "instructions": function_instructions, "liveness": {"in": ["v0"], "out": []}}]}
    return {"type": "Object", "O_1": {"blocks": [main_block], "functions": {"f": function}, "subObjects": {}}}


# The JSON lists the arguments in reverse order: mstore(p, v) is {"in": [v, p]}
FIXED_ACCESSES = [{"in": ["v0", "0x01c0"], "op": "mstore", "out": []},
                  {"in": ["0x20", "0x0200"], "op": "keccak256", "out": ["v1"]},
                  {"in": ["v1", "0x0300"], "op": "mstore", "out": []},
                  {"in": ["v1", "0x60", "0x0240"], "op": "calldatacopy", "out": []},
                  # A variable offset cannot be bounded and a zero size accesses nothing
                  {"in": ["0x20", "v0"], "op": "keccak256", "out": ["v2"]},
                  {"in": ["0x00", "0x0400"], "op": "return", "out": []}]


def test_largest_constant_access_without_memoryguard():
    free_memory_pointer = {"in": ["0x80", "0x40"], "op": "mstore", "out": []}
    cfg = parse_CFG_from_json_dict({"O": object_json(free_memory_pointer, FIXED_ACCESSES)})["O"]
    cfg_object = cfg.get_object("O_1")
    # mstore(0x300, v1) is the highest access: [0x300, 0x320)
    assert largest_constant_memory_access(cfg_object) == 0x320
    assert spill_base(cfg_object) == "320"


def test_memoryguard_is_the_base():
    guard = {"in": [], "literalArgs": ["0x80"], "op": "memoryguard", "out": ["v9"]}
    cfg = parse_CFG_from_json_dict({"O": object_json(guard, FIXED_ACCESSES)})["O"]
    assert int(spill_base(cfg.get_object("O_1")), 16) == 0x80


def run_f(creation_code: str) -> str:
    runtime_code = subprocess.run(["evm", "run", "--create", creation_code], check=True, capture_output=True,
                                  text=True).stdout.strip()
    calldata = "5eb69a95" + "".join(f"{value:064x}" for value in [3, 5, 7, 11, 13, 17])
    return subprocess.run(["evm", "run", "--input", calldata, runtime_code], check=True, capture_output=True,
                          text=True).stdout.strip()


@pytest.mark.slow
@pytest.mark.skipif(shutil.which("evm") is None, reason="needs geth's evm")
def test_spill_does_not_overwrite_fixed_addresses(tmp_path: Path):
    # With -d 8, the function spills values to memory, which must not overwrite the assembly's words at 0x80 / 0xa0
    output_folder = tmp_path.joinpath("grey")
    subprocess.run(["python3", str(REPO_ROOT.joinpath("src/grey_main.py")), "-s", str(FIXED_MEMORY_CONTRACT),
                    "-o", str(output_folder), "-if", "sol", "-solc", str(SOLC), "-d", "8", "--debug"],
                   cwd=tmp_path, check=True, capture_output=True)
    assert pd.read_csv(next(output_folder.glob("repair_*.csv")))["memory_slots"].sum() > 0
    grey_creation_code = pd.read_csv(output_folder.joinpath(f"{FIXED_MEMORY_CONTRACT.stem}.csv"))["bin_code"][0]
    solc_output = subprocess.run([str(SOLC), "--via-ir", "--optimize", "--bin", str(FIXED_MEMORY_CONTRACT)],
                                 check=True, capture_output=True, text=True).stdout
    assert run_f(grey_creation_code) == run_f(solc_output.strip().splitlines()[-1])
