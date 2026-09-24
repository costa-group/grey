"""
Regression test: grey must generate the same bytecode regardless of the hash seed used by Python.
Iterating over sets of strings in a way that reaches the output breaks this property
(see scripts/detect_nondeterminism.py to locate the stage responsible).
"""
import os
import subprocess
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_MOST_CALLED = REPO_ROOT.joinpath("examples/most_called_0_8/test_most_called")
SOLC = REPO_ROOT.joinpath("examples/solc-without-opt")

# Small inputs that go through the reparation phase with -d 8. The second one produced
# different bytecode sizes depending on the seed before making the passes deterministic
INPUTS = ["0x6e79b51959cf968d87826592f46f819f92466615", "0x086f405146ce90135750bbec9a063a8b20a8bffb"]


def bytecode_with_seed(address: str, seed: str, output_folder: Path) -> pd.DataFrame:
    source = TEST_MOST_CALLED.joinpath(address, f"{address}_standard_input.json")
    command = ["python3", str(REPO_ROOT.joinpath("src/grey_main.py")), "-s", str(source), "-o", str(output_folder),
               "-if", "standard-json", "-solc", str(SOLC), "-d", "8", "--no-inline"]
    environment = {**os.environ, "PYTHONHASHSEED": seed}
    subprocess.run(command, cwd=output_folder.parent, env=environment, check=True, capture_output=True)
    return pd.read_csv(output_folder.joinpath(f"{source.stem}.csv"))[["contract", "bin_code"]]


@pytest.mark.slow
@pytest.mark.parametrize("address", INPUTS)
def test_same_bytecode_with_different_seeds(address: str, tmp_path: Path):
    bytecode_seed_1 = bytecode_with_seed(address, "1", tmp_path.joinpath("seed_1"))
    bytecode_seed_2 = bytecode_with_seed(address, "2", tmp_path.joinpath("seed_2"))
    assert bytecode_seed_1.equals(bytecode_seed_2), f"Bytecode of {address} depends on the hash seed"
