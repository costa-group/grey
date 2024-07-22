import argparse
from pathlib import Path
from timeit import default_timer as dtimer
import pandas as pd

from parser.parser import parse_CFG
from parser.cfg import store_sfs_json
from greedy.greedy import greedy_standalone
from statistics.statistics import generate_statistics_info
from liveness.liveness_analysis import dot_from_analysis, perform_liveness_analysis


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

    if args.visualize:
        dot_file_dir = final_dir.joinpath("liveness")
        dot_file_dir.mkdir(exist_ok=True, parents=True)
        liveness_info = dot_from_analysis(cfg, dot_file_dir)
    else:
        liveness_info = perform_liveness_analysis(cfg)

    result_objects, results_functions = cfg.build_spec_for_objects()

    for obj in result_objects:
        results = result_objects[obj]
        store_sfs_json(results, final_dir)

        if args.greedy:
            csv_rows = []
            for sfs_dict_list in results:
                for sfs_dict_name in sfs_dict_list:
                    sfs_dict = sfs_dict_list[sfs_dict_name]
                    outcome, time, solution_found = greedy_standalone(sfs_dict)
                    csv_row = generate_statistics_info(solution_found, outcome, time, sfs_dict)
                    csv_rows.append(csv_row)
            df = pd.DataFrame(csv_rows)
            df.to_csv("outcome.csv")