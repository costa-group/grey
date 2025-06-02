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
import greedy.greedy as new_greedy
from solution_generation.statistics import generate_statistics_info


def cfg_block_spec_ids(cfg_block: CFGBlock) -> Tuple[str, float, List[instr_id_T]]:
    outcome1, time1, greedy_ids1 = previous.greedy_standalone(cfg_block.spec)
    outcome2, time2, greedy_ids2 = new_greedy.greedy_standalone(cfg_block.spec)
    if greedy_ids2 is not None and (outcome1 == "error" or len(greedy_ids1) > len(greedy_ids2)):
        outcome = outcome2
        time = time2
        greedy_ids = greedy_ids2
        # print("GANA Nuevo", cfg_block.block_id, "IDS viejo", greedy_ids1, "IDS nuevo", greedy_ids2)
        # print("Outcome Viejo", outcome1, "Outcome nuevo", outcome2)

        # print(cfg_block.block_id, len(greedy_ids1), len(greedy_ids2))
        # print(len(greedy_ids))

    elif greedy_ids2 is not None and (len(greedy_ids1) < len(greedy_ids2) or outcome2 == "error"):
        outcome = outcome1
        time = time1
        greedy_ids = greedy_ids1
        # print("GANA Viejo", cfg_block.block_id, "IDS viejo", greedy_ids1, "IDS nuevo", greedy_ids2)
        # print("Outcome Viejo", outcome1, "Outcome nuevo", outcome2)
        # print(cfg_block.block_id, len(greedy_ids1), len(greedy_ids2))
        # print(len(greedy_ids))

    else:
        outcome = outcome1
        time = min(time1, time2)
        greedy_ids = greedy_ids1

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
