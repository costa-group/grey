"""
Module to insert the JUMP, JUMPI and PUSH [tag] instructions before performing the liveness analysis
"""
from typing import Dict
from global_params.types import block_id_T
from parser.cfg import CFG
from parser.cfg_block_list import CFGBlockList


def insert_jumps_tags_cfg(cfg: CFG) -> Dict[str, Dict[str, int]]:
    """
    Introduces the JUMP, JUMPI and PUSH [tag] instructions in the blocks according to the CFG structure
    """
    combined_tags = dict()
    for object_id, cfg_object in cfg.objectCFG.items():
        tags_object = dict()

        # First we generate the tags for the functions
        insert_jumps_tags_block_list(cfg_object.blocks, tags_object)

        for function_name, cfg_function in cfg_object.functions.items():
            insert_jumps_tags_block_list(cfg_function.blocks, tags_object)

        combined_tags[object_id] = tags_object

        sub_object = cfg.get_subobject()

        if sub_object is not None:
            tags_sub_object = insert_jumps_tags_cfg(sub_object)
            combined_tags |= tags_sub_object

    return combined_tags


def insert_jumps_tags_block_list(cfg_block_list: CFGBlockList, tags_dict: Dict[str, int]) -> None:
    for block_name, block in cfg_block_list.blocks.items():
        block.insert_jumps_tags(tags_dict)
