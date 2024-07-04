#!/usr/bin/python3

import sys
import os
import argparse
from pathlib import Path
from timeit import default_timer as dtimer

from parser.parser import parse_CFG
from parser.cfg import store_sfs_json

def parse_args():    
    global args

    parser = argparse.ArgumentParser(description="GREEN Project")

    parser.add_argument("-s",  "--source",    type=str, help="local source file name.")
    parser.add_argument("-o",  "--folder",    type=str, help="Dir to store the results.")

    args = parser.parse_args()


if __name__ == "__main__":
    global args
    
    print("Green Main")
    parse_args()

    x = dtimer()
    
    cfg = parse_CFG(args.source)

    y = dtimer()

    print("CFG Parser: "+str(y-x)+"s")

    results = cfg.build_spec_for_blocks()
    final_dir = Path(args.folder)
    final_dir.mkdir(exist_ok=True, parents=True)
    store_sfs_json(results, final_dir)
