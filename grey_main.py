import sys
import os
import argparse

import parser.parser


def parse_args():    
    global args

    parser = argparse.ArgumentParser(description="GREEN Project")
    group = parser.add_mutually_exclusive_group(required=True)

    group.add_argument("-s",  "--source",    type=str, help="local source file name.")




if __name__ == "__main__":
    global args
    
    print("Green Main")
    parse_args()

    parser.parse_CFG(args.source)
    
