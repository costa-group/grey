"""
The outputs of a function call must follow the order of the values returned by the function, whatever its name.
Function calls used to be identified by an underscore in their name, so a function defined in inline assembly
(named 'usr$<name>', without solc's id suffix) with several return values got them swapped.
"""
import shutil
import subprocess
from pathlib import Path

import pandas as pd
import pytest

from parser.parser import parse_CFG_from_json_dict

REPO_ROOT = Path(__file__).resolve().parent.parent
SOLC = REPO_ROOT.joinpath("examples/solc-without-opt")
MULTIPLE_RETURNS_CONTRACT = Path(__file__).resolve().parent.joinpath("files/multiple_returns_assembly.sol")


def two_returns_function():
    return {"arguments": [], "entry": "Block0", "numReturns": 2, "type": "Function",
            "blocks": [{"id": "Block0", "type": "BuiltinCall",
                        "exit": {"returnValues": ["v0", "v1"], "type": "FunctionReturn"},
                        "instructions": [{"in": ["0x00"], "op": "calldataload", "out": ["v0"]},
                                         {"in": ["0x20"], "op": "calldataload", "out": ["v1"]}],
                        "liveness": {"in": [], "out": ["v0", "v1"]}}]}


def cfg_json_with_calls():
    """
    A main block that calls the same function with and without an underscore in its name
    """
    instructions = [{"in": [], "op": "fun_pair_12", "out": ["v0", "v1"]},
                    {"in": [], "op": "usr$pair", "out": ["v2", "v3"]},
                    {"in": ["v0", "v1", "v2", "v3"], "op": "log2", "out": []}]
    main_block = {"id": "Block0", "type": "FunctionCall", "exit": {"type": "Terminated"},
                  "instructions": instructions, "liveness": {"in": [], "out": []}}
    return {"type": "Object", "Calls_1": {"blocks": [main_block], "subObjects": {},
                                          "functions": {"fun_pair_12": two_returns_function(),
                                                        "usr$pair": two_returns_function()}}}


def test_every_function_call_keeps_the_order_of_its_outputs():
    cfg = parse_CFG_from_json_dict({"Calls": cfg_json_with_calls()})["Calls"]
    instructions = cfg.get_object("Calls_1").blocks.get_block("Calls_1_Block0").get_instructions()
    out_args_by_op = {instruction.get_op_name(): instruction.get_out_args() for instruction in instructions}

    # The first returned value is on top of the stack after the call, as in the functionReturn of the callee
    assert out_args_by_op["fun_pair_12"] == ["v0", "v1"]
    assert out_args_by_op["usr$pair"] == ["v2", "v3"]


def run_g(creation_code: str) -> str:
    runtime_code = subprocess.run(["evm", "run", "--create", creation_code], check=True, capture_output=True,
                                  text=True).stdout.strip()
    # g(5, 7)
    calldata = "1cd65ae4" + f"{5:064x}" + f"{7:064x}"
    return subprocess.run(["evm", "run", "--input", calldata, runtime_code], check=True, capture_output=True,
                          text=True).stdout.strip()


@pytest.mark.slow
@pytest.mark.skipif(shutil.which("evm") is None, reason="needs geth's evm")
@pytest.mark.parametrize("flags", [[], ["--no-inline"]])
def test_assembly_function_with_two_returns_matches_solc(flags, tmp_path: Path):
    output_folder = tmp_path.joinpath("grey")
    subprocess.run(["python3", str(REPO_ROOT.joinpath("src/grey_main.py")), "-s", str(MULTIPLE_RETURNS_CONTRACT),
                    "-o", str(output_folder), "-if", "sol", "-solc", str(SOLC)] + flags,
                   cwd=tmp_path, check=True, capture_output=True)
    grey_creation_code = pd.read_csv(output_folder.joinpath(f"{MULTIPLE_RETURNS_CONTRACT.stem}.csv"))["bin_code"][0]

    solc_output = subprocess.run([str(SOLC), "--via-ir", "--bin", str(MULTIPLE_RETURNS_CONTRACT)], check=True,
                                 capture_output=True, text=True).stdout
    solc_creation_code = solc_output.strip().splitlines()[-1]

    assert run_g(grey_creation_code) == run_g(solc_creation_code)
