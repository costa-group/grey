"""
Runs grey with every equivalent-block merge forced, i.e. with the profitability check of the merge pass
disabled (cfg_methods.equivalent_blocks_merging._region_is_profitable always true). Combined with --debug,
it stresses the correctness of the merge pass and of the phases after it (layouts, greedy, reparation, emission).

Usage (from the repo root, with any grey arguments):
  python3 scripts/stress_forced_merges.py -s <input> -o <out_dir> -if standard-json -solc <solc> --debug [grey flags]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.joinpath("src")))

import cfg_methods.equivalent_blocks_merging as merging  # noqa: E402

merging._region_is_profitable = lambda *args: True

from execution.args_parser import parse_args  # noqa: E402
from execution.main_execution import main  # noqa: E402

main(parse_args())
