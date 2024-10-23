"""
Module used to generate the sub blocks and count how many times each function is invoked.
Same idea as optimizable_block_list but using the cfg actions and simplifying the process
"""
from parser.cfg_block_list import CFGBlockList
from parser.cfg import CFG
import parser.constants as constants
from parser.cfg_block_actions.split_block import SplitBlock


def split_blocks_cfg(cfg: CFG) -> None:
    """
    Splits the blocks in the cfg
    """
    for object_id, cfg_object in cfg.objectCFG.items():
        modify_block_list_split(cfg_object.blocks)

        # We also consider the information per function
        for function_name, cfg_function in cfg_object.functions.items():
            modify_block_list_split(cfg_function.blocks)

        sub_object = cfg.get_subobject()

        if sub_object is not None:
            split_blocks_cfg(sub_object)


def modify_block_list_split(block_list: CFGBlockList) -> None:
    """
    Modifies a CFGBlockList by splitting blocks when function calls and split instructions are found
    """
    blocks_to_traverse = list(block_list.blocks.items())
    new_start_block = None
    for block_name, cfg_block in blocks_to_traverse:

        # It can be reassigned if the block is split multiple times
        current_block = cfg_block
        instr_idx = 0

        while instr_idx < len(current_block.get_instructions()):
            instr = current_block.get_instructions()[instr_idx]

            is_split_instr = instr.get_op_name() in constants.split_block
            is_function_call = instr.get_op_name() in cfg_block.function_calls
            is_jump = instr.get_op_name() in ["JUMP", "JUMPI"]

            if is_split_instr or is_function_call or is_jump:
                # Sub blocks contain a split instruction or a function call as the last instruction
                split_block_action = SplitBlock(instr_idx, current_block, block_list)
                split_block_action.perform_action()

                # If the current block corresponds to the initial block and we modify it
                if new_start_block is None and current_block.block_id == block_list.start_block:
                    new_start_block = split_block_action.first_half

                current_block = split_block_action.second_half
                instr_idx = 0
            else:
                instr_idx += 1
