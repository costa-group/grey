#!/usr/bin/python3

import logging
from execution.main_execution import main
from execution.args_parser import parse_args

if __name__ == "__main__":
    # logging.basicConfig(level=logging.DEBUG)
    main(parse_args())
