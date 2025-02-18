"""
Module to insert the JUMP, JUMPI and PUSH [tag] instructions before performing the liveness analysis
"""
from typing import Dict, Iterable, Optional
from global_params.types import block_id_T, function_name_T, cfg_object_T
from parser.cfg import CFG
from parser.cfg_function import CFGFunction
from parser.cfg_block_list import CFGBlockList
from parser.cfg_block import CFGBlock


def insert_jumps_tags_cfg(cfg: CFG) -> Dict[cfg_object_T, Dict[block_id_T, int]]:
    """
    Introduces the JUMP, JUMPI and PUSH [tag] instructions in the blocks according to the CFG structure
    """
    combined_tags = dict()
    for object_id, cfg_object in cfg.objectCFG.items():
        tags_object = dict()

        # First we generate the tags for the functions
        insert_jumps_tags_block_list(cfg_object.blocks, tags_object)

        for function_name, cfg_function in cfg_object.functions.items():
            start_block_id = cfg_function.blocks.start_block
            # Insert a tag for the initial block of the function
            tag_from_tag_dict(start_block_id, tags_object)

            # We need to pass an additional parameter as the initial value
            return_value = f"out_{function_name}"
            cfg_function.arguments.insert(0, return_value)

            # Insert the tags and jumps of the block list
            insert_jumps_tags_block_list(cfg_function.blocks, tags_object, return_value)

        combined_tags[object_id] = tags_object

        sub_object = cfg_object.get_subobject()

        if sub_object is not None:
            tags_sub_object = insert_jumps_tags_cfg(sub_object)
            combined_tags |= tags_sub_object

    return combined_tags


def insert_jumps_tags_block_list(cfg_block_list: CFGBlockList, tags_dict: Dict[str, int],
                                 jump_value: Optional[str] = None) -> None:
    for block_name, block in cfg_block_list.blocks.items():
        if block.get_jump_type() == "unconditional":
            jumps_to_tag = tag_from_tag_dict(block.get_jump_to(), tags_dict)
            block.insert_jump_instruction(str(jumps_to_tag))
        elif block.get_jump_type() == "conditional":
            jumps_to_tag = tag_from_tag_dict(block.get_jump_to(), tags_dict)
            block.insert_jumpi_instruction(str(jumps_to_tag))
        elif block.get_jump_type() == "FunctionReturn":
            # For function returns, we need to insert the jump target
            return_instruction = block.get_instructions()[-1]
            assert return_instruction.op == "functionReturn", "Function return blocks must " \
                                                              f"have functionReturn instructions: {return_instruction}"
            return_instruction.in_args.insert(0, jump_value)


def tag_from_tag_dict(block_id: block_id_T, tags_dict: Dict[block_id_T, int]) -> int:
    """
    Retrieve a value from the given tag dict, assigning a valid value if the corresponding block
    id is not in the tag dict yet
    """
    tag_value = tags_dict.get(block_id, None)
    if tag_value is None:
        tag_value = len(tags_dict) + 1
        tags_dict[block_id] = tag_value
    return tag_value
