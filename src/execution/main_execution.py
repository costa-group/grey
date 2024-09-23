import argparse
from pathlib import Path
from timeit import default_timer as dtimer
import pandas as pd

from parser.optimizable_block_list import compute_sub_block_cfg
from parser.parser import parse_CFG
from parser.cfg import store_sfs_json
from greedy.greedy import greedy_standalone
from solution_generation.statistics import generate_statistics_info
from solution_generation.reconstruct_bytecode import asm_from_ids
from liveness.liveness_analysis import dot_from_analysis, perform_liveness_analysis
from liveness.layout_generation import layout_generation


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GREEN Project")

    parser.add_argument("-s",  "--source",    type=str, help="local source file name.")
    parser.add_argument("-o",  "--folder",    type=str, help="Dir to store the results.", default="/tmp/grey/")
    parser.add_argument("-g", "--greedy", action="store_true", help="Enables the greedy algorithm")
    parser.add_argument("-v", "--visualize", action="store_true", dest="visualize",
                        help="Generates a dot file for each object in the JSON, "
                             "showcasing the results from the liveness analysis")

    args = parser.parse_args()
    return args


def main():
    print("Green Main")
    args = parse_args()

    x = dtimer()

    cfg = parse_CFG(args.source)

    y = dtimer()

    print("CFG Parser: "+str(y-x)+"s")

    final_dir = Path(args.folder)

    final_dir.mkdir(exist_ok=True, parents=True)

    dot_file_dir = final_dir.joinpath("liveness")
    dot_file_dir.mkdir(exist_ok=True, parents=True)

    sub_block_cfg = compute_sub_block_cfg(cfg)

    if args.visualize:
        liveness_info = dot_from_analysis(sub_block_cfg, dot_file_dir)

    x = dtimer()
    jsons = layout_generation(sub_block_cfg, dot_file_dir)
    sfs_final_dir = final_dir.joinpath("sfs")
    sfs_final_dir.mkdir(exist_ok=True, parents=True)
    y = dtimer()

    print("Layout generation: " + str(y - x) + "s")

    block_name2asm = dict()
    if args.greedy:
        csv_rows = []
        for block_name, sfs in jsons.items():
            store_sfs_json(block_name, sfs, sfs_final_dir)

            _, time, solution_found = greedy_standalone(sfs)
            csv_row = generate_statistics_info(block_name, solution_found, time, sfs)
            solution_asm = asm_from_ids(sfs, solution_found)
            block_name2asm[block_name] = solution_asm
            csv_rows.append(csv_row)

        # Generate complete asm from CFG object + dict

        df = pd.DataFrame(csv_rows)
        df.to_csv(final_dir.joinpath("statistics.csv"))
