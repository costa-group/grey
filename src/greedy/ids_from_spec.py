"""
Module that handles the generation of the ids from the greedy algorithm.
"""
from pathlib import Path
from typing import Tuple, List, Dict, Optional

import pandas as pd

from global_params.types import instr_id_T
from parser.cfg_block import CFGBlock
from parser.cfg_block_list import CFGBlockList
from parser.cfg_object import CFGObject
from parser.cfg import CFG
from greedy.greedy import greedy_standalone
from solution_generation.statistics import generate_statistics_info


def cfg_block_spec_ids(cfg_block: CFGBlock) -> Tuple[str, float, List[instr_id_T]]:
    outcome, time, greedy_ids = greedy_standalone(cfg_block.spec)
    cfg_block.greedy_ids = greedy_ids
    return outcome, time, greedy_ids


def cfg_block_list_spec_ids(cfg_blocklist: CFGBlockList) -> List[Dict]:
    """
    Generates the assembly code of all the blocks in a block list and returns the statistics
    """
    csv_dicts = []
    for block_name, block in cfg_blocklist.blocks.items():
        outcome, time, greedy_ids = cfg_block_spec_ids(block)
        csv_dicts.append(generate_statistics_info(block_name, greedy_ids, time, block.spec))
    return csv_dicts


def cfg_object_spec_ids(cfg: CFGObject):
    """
    Generates the assembly code for a
    """
    csv_dicts = cfg_block_list_spec_ids(cfg.blocks)
    for cfg_function in cfg.functions.values():
        csv_dicts.extend(cfg_block_list_spec_ids(cfg_function.blocks))
    return csv_dicts


def recursive_cfg_spec_ids(cfg: CFG):
    """
    Generates the assembly for all the blocks inside the CFG, excluding the sub objects.
    """
    csv_dicts = []
    for cfg_object in cfg.get_objects().values():
        csv_dicts.extend(cfg_object_spec_ids(cfg_object))
        sub_object = cfg_object.subObject
        if sub_object is not None:
            csv_dicts.extend(recursive_cfg_spec_ids(sub_object))
    return csv_dicts


def cfg_spec_ids(cfg: CFG, csv_file: Optional[Path]) -> None:
    """
    Generates the greedy ids from the specification inside the cfg and stores in the field "greedy_ids" inside
    each block. Stores the information from the greedy generation in a csv file
    """
    csv_dicts = recursive_cfg_spec_ids(cfg)
    pd.DataFrame(csv_dicts).to_csv(csv_file)
