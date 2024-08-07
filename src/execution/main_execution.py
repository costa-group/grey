import argparse
from pathlib import Path
from timeit import default_timer as dtimer
import pandas as pd

from parser.parser import parse_CFG
from parser.cfg import store_sfs_json
from greedy.greedy import greedy_standalone
from statistics.statistics import generate_statistics_info
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

    if args.visualize:
        liveness_info = dot_from_analysis(cfg, dot_file_dir)
    else:
        liveness_info = perform_liveness_analysis(cfg)

    x = dtimer()
    jsons = layout_generation(cfg, dot_file_dir)
    sfs_final_dir = final_dir.joinpath("sfs")
    sfs_final_dir.mkdir(exist_ok=True, parents=True)
    y = dtimer()

    print("Layout generation: " + str(y - x) + "s")

    if args.greedy:
        csv_rows = []
        for block_name, sfs in jsons.items():
            store_sfs_json(sfs, sfs_final_dir)

            outcome, time, solution_found = greedy_standalone(sfs)
            csv_row = generate_statistics_info(block_name, solution_found, outcome, time, sfs)
            csv_rows.append(csv_row)
        df = pd.DataFrame(csv_rows)
        df.to_csv("outcome.csv")
