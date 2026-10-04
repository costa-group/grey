"""
Verbatims (only available in Yul) end a sub-block and are emitted as VERBATIM items with their bytes. As the other
builtins, the last of their outputs is on top of the stack after them.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pandas as pd
import pytest

from parser import constants
from parser.cfg_instruction import CFGInstruction

REPO_ROOT = Path(__file__).resolve().parent.parent
SOLC = REPO_ROOT.joinpath("examples/solc-without-opt")
VERBATIM_CONTRACT = Path(__file__).resolve().parent.joinpath("files/verbatim_outputs.yul")


def test_verbatim_is_a_split_instruction_with_the_builtin_order():
    instruction = CFGInstruction("verbatim_1i_2o", ["v0"], ["v1", "v2"])
    assert "verbatim_1i_2o" in constants.split_block
    assert instruction.get_out_args() == ["v2", "v1"]


def evm_output(code: str, calldata: str) -> str:
    return subprocess.run(["evm", "run", "--input", calldata, code], check=True, capture_output=True,
                          text=True).stdout.strip()


@pytest.mark.slow
@pytest.mark.skipif(shutil.which("evm") is None, reason="needs geth's evm")
def test_verbatims_match_solc(tmp_path: Path):
    standard_input = tmp_path.joinpath("verbatim_outputs_standard_input.json")
    standard_input.write_text(json.dumps({"language": "Yul",
                                          "sources": {"verbatim_outputs.yul": {"content": VERBATIM_CONTRACT.read_text()}},
                                          "settings": {"optimizer": {"enabled": True}}}))
    output_folder = tmp_path.joinpath("grey")
    subprocess.run(["python3", str(REPO_ROOT.joinpath("src/grey_main.py")), "-s", str(standard_input),
                    "-o", str(output_folder), "-if", "standard-json", "-solc", str(SOLC), "--debug"],
                   cwd=tmp_path, check=True, capture_output=True)
    grey_code = pd.read_csv(output_folder.joinpath(f"{standard_input.stem}.csv"))["bin_code"][0]

    solc_output = subprocess.run([str(SOLC), "--strict-assembly", "--bin", str(VERBATIM_CONTRACT)], check=True,
                                 capture_output=True, text=True).stdout
    solc_code = solc_output.strip().splitlines()[-1]

    # The code runs directly (a Yul object without subobjects): returns (y - 0, x, 0) for the calldata (x, y)
    calldata = f"{0x1111:064x}" + f"{0x2222:064x}"
    assert evm_output(grey_code, calldata) == evm_output(solc_code, calldata) == \
           "0x" + f"{0x2222:064x}" + f"{0x1111:064x}" + f"{0:064x}"
