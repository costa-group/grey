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
import greedy.greedy_previous as previous
from solution_generation.statistics import generate_statistics_info
from greedy.greedy_info import GreedyInfo
import greedy.greedy_new_version as alternative
import numpy as np


def _length_or_zero(l, outcome):
    return len(l) if l is not None and outcome != "error" else 10000


def cfg_block_spec_ids(cfg_block: CFGBlock) -> Tuple[str, float, List[instr_id_T]]:
    # Retrieve the information from each of the executions
    outcome1, time1, greedy_ids1 = previous.greedy_standalone(cfg_block.spec, cfg_block.spec["admits_junk"])
    greedy_info = GreedyInfo.from_old_version(greedy_ids1, outcome1, time1, cfg_block.spec["user_instrs"])

    # greedy_info3 = alternative.greedy_standalone(cfg_block.spec)
    # outcome3, time3, greedy_ids3 = greedy_info3.outcome, greedy_info3.execution_time, greedy_info3.greedy_ids

    lengths = [_length_or_zero(greedy_ids1, outcome1),
               # _length_or_zero(greedy_ids3, outcome3)
               ]

    chosen_idx = np.argmin(lengths)
    print(chosen_idx, lengths)

    outcome = outcome1 # [outcome1, outcome3][chosen_idx]
    time = time1 #  [time1, time3][chosen_idx]
    greedy_ids = greedy_ids1 # [greedy_ids1, greedy_ids3][chosen_idx]

    cfg_block.greedy_ids = greedy_ids if greedy_ids is not None else []
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


def cfg_spec_ids(cfg: CFG, csv_file: Optional[Path], visualize: bool) -> None:
    """
    Generates the greedy ids from the specification inside the cfg and stores in the field "greedy_ids" inside
    each block. Stores the information from the greedy generation in a csv file
    """
    csv_dicts = recursive_cfg_spec_ids(cfg)
    if visualize:
        pd.DataFrame(csv_dicts).to_csv(csv_file)
