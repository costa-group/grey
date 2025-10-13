"""
Main methods to repairing the stack-too-deep placeholders
"""
from typing import List, Dict, Tuple, Set
from parser.parser import CFGBlockList
from global_params.types import var_id_T


def repair_unreachable_blocklist(cfg_blocklist: CFGBlockList, elements_to_fix: Set[var_id_T]):
    """
    Assumes the blocks in the cfg contain the information of the
    greedy algorithm according to greedy algorithm
    """
    compute
