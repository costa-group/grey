#!/usr/bin/python3

import sys
import os
import argparse
from timeit import default_timer as dtimer

from parser.parser import parse_CFG


def parse_args():    
    global args

    parser = argparse.ArgumentParser(description="GREEN Project")
    group = parser.add_mutually_exclusive_group(required=True)

    group.add_argument("-s",  "--source",    type=str, help="local source file name.")

    args = parser.parse_args()


if __name__ == "__main__":
    global args
    
    print("Green Main")
    parse_args()

    x = dtimer()
    
    parse_CFG(args.source)

    y = dtimer()

    print("CFG Parser: "+str(y-x)+"s")
