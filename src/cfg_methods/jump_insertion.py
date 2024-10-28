"""
Module to insert the JUMP, JUMPI and PUSH [tag] instructions before performing the liveness analysis
"""
from parser.cfg import CFG


def insert_jump_instructions(cfg: CFG):
    """
    Introduces the JUMP, JUMPI and PUSH [tag] instructions in the blocks according to the CFG structure
    """
    pass
