#!/usr/bin/python3

import sys
import os
import argparse
from pathlib import Path
from timeit import default_timer as dtimer
import pandas as pd

from parser.parser import parse_CFG
from parser.cfg import store_sfs_json
from greedy.greedy import greedy_standalone
from statistics.statistics import generate_statistics_info

def parse_args():    
    global args

    parser = argparse.ArgumentParser(description="GREEN Project")

    parser.add_argument("-s",  "--source",    type=str, help="local source file name.")
    parser.add_argument("-o",  "--folder",    type=str, help="Dir to store the results.", default="/tmp/grey/")
    parser.add_argument("-g", "--greedy", action="store_true", help="Enables the greedy algorithm")

    args = parser.parse_args()


if __name__ == "__main__":
    global args
    
    print("Green Main")
    parse_args()

    x = dtimer()
    
    cfg = parse_CFG(args.source)

    y = dtimer()

    print("CFG Parser: "+str(y-x)+"s")

    result_objects = cfg.build_spec_for_objects()
    final_dir = Path(args.folder)

    final_dir.mkdir(exist_ok=True, parents=True)

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
