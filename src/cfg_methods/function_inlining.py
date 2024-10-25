"""
Module to perform function inlining.
"""
from typing import Set, Dict, Tuple, List
from collections import defaultdict
from global_params.types import block_id_T, component_name_T, function_name_T, block_list_id_T
from parser.cfg_block import CFGBlock
from analysis.cfg_validation import validate_block_list_comes_from
from parser.cfg_block_list import CFGBlockList
from parser.cfg_object import CFGObject
from parser.cfg import CFG
from parser.cfg_block_actions.inline_function import InlineFunction
import networkx as nx
import matplotlib.pyplot as plt

# For each time a function is invoked, we store the position of the instruction (int) in the
# block (blok_id_T) that appears in the block list (block_list_id)
function_call_info_T = Dict[str, List[Tuple[int, block_id_T, block_list_id_T]]]


def inline_functions(cfg: CFG) -> None:
    """
    Inlines the functions that are invoked just in one place
    """
    cfg_object2modify: Dict[component_name_T, function_call_info_T] = generate_function2information(cfg)
    for object_id, cfg_object in cfg.objectCFG.items():
        inline_functions_cfg_object(cfg_object, cfg_object2modify[object_id])
        sub_object = cfg.get_subobject()

        if sub_object is not None:
            inline_functions(sub_object)


# Methods to compute the invocation information

def generate_function2information(cfg: CFG) -> Dict[function_name_T, function_call_info_T]:
    """
    For each cfg object, a dictionary is produced that links each function to the position, block and block list
    in which it is used
    """
    function2blocks = dict()
    for object_id, cfg_object in cfg.objectCFG.items():
        current_function2blocks = dict()
        function_names = set(cfg_object.functions.keys())
        current_function2blocks.update(generate_function2blocks_block_list(cfg_object.blocks, function_names))

        # We also consider the information per function
        for cfg_function in cfg_object.functions.values():
            current_function2blocks.update(generate_function2blocks_block_list(cfg_function.blocks, function_names))

        function2blocks[object_id] = current_function2blocks
        sub_object = cfg.get_subobject()

        if sub_object is not None:
            function2blocks.update(generate_function2information(sub_object))

    return function2blocks


def generate_function2blocks_block_list(cfg_block_list: CFGBlockList, function_names: Set[function_name_T]) -> function_call_info_T:
    """
    Links the function calls that appear in the block list to the exact block and the block list
    """
    function2blocks = defaultdict(lambda: [])
    for block_name, block in cfg_block_list.blocks.items():
        for i, instruction in enumerate(block.get_instructions()):
            if instruction.get_op_name() in function_names:
                function2blocks[instruction.get_op_name()].append((i, block.block_id, cfg_block_list.name))
    return function2blocks


# Methods to perform the inlining of cfg objects
def inline_functions_cfg_object(cfg_object: CFGObject, function_call_info: function_call_info_T):
    # Dict that maps each initial block name in the CFG to the set of blocks in which it can be split
    block2current: Dict[block_id_T, List[block_id_T]] = dict()

    # Same idea as before but for block lists (as we have joined them previously)
    block_list2current: Dict[block_list_id_T, block_list_id_T] = dict()

    for function_name, call_info in function_call_info.items():

        # Only consider blocks for inlining that have just one invocation
        if len(call_info) == 1:
            instr_pos, cfg_block_name, cfg_block_list_name = call_info[0]

            # First we find in which block list the function block list is stored
            # As many substitutions can happen, we have to iterate recursively to find the most recent one
            current_block_list_name = _find_current_block_list(cfg_block_list_name, block_list2current)
            cfg_block_list = cfg_object.get_block_list(current_block_list_name)

            # Then we determine whether the function has been split
            split_blocks = block2current.get(cfg_block_name, [cfg_block_name])

            # We have to determine the corresponding index if there are multiple blocks
            if len(split_blocks) > 1:
                split_block_index, position_index = _determine_idx(instr_pos, split_blocks, cfg_block_list)
            else:
                split_block_index, position_index = 0, instr_pos

            inline_action = InlineFunction(position_index, cfg_block_list.blocks[split_blocks[split_block_index]],
                                           cfg_block_list, function_name, cfg_object)
            inline_action.perform_action()

            # Uncomment for validation
            # is_correct, reason = validate_block_list_comes_from(cfg_block_list)

            # Finally, we have to update the information of both the block lists and blocks
            block_list2current[function_name] = current_block_list_name
            block2current[cfg_block_name] = split_blocks[:split_block_index] + \
                                            [inline_action.first_sub_block.block_id,
                                             inline_action.second_sub_block.block_id] + split_blocks[split_block_index+1:]


def _determine_idx(instr_idx: int, split_block_names: List[block_id_T], cfg_block_list: CFGBlockList) \
        -> Tuple[int, int]:
    """
    Determines the index of the block in the list of the split_block_names contains the original index "instr_idx"
    and the relative index of the instruction according to that block
    """
    found_idx = False
    i = 0
    while i < len(split_block_names) and not found_idx:
        cfg_block = cfg_block_list.blocks[split_block_names[i]]

        # The instr index corresponds to this block
        if instr_idx < len(cfg_block.get_instructions()):
            return i, instr_idx
        # We have to remove an extra instruction, as the previous function calls have been removed
        instr_idx -= len(cfg_block.get_instructions()) + 1
        i += 1
    raise ValueError("Block not found")


def _find_current_block_list(block_list_name: block_list_id_T,
                             block_list2current: Dict[block_list_id_T, block_list_id_T]) -> block_id_T:
    """
    Following the idea of a union-find, determine which is to which block
    list the current block is associated
    """
    next_block_list = block_list2current.get(block_list_name, block_list_name)
    if next_block_list == block_list_name:
        return block_list_name
    else:
        answer_block_list = _find_current_block_list(next_block_list, block_list2current)
        block_list2current[block_list_name] = answer_block_list
        return answer_block_list
