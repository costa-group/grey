"""
Module that generates a list of sub-blocks to optimize using the greedy algorithm from the given ones
"""
import itertools
from copy import deepcopy
from typing import List, Dict, Tuple
from parser.cfg_instruction import CFGInstruction
from parser.cfg_block_list import CFGBlockList, CFGBlock
from parser.cfg import CFG
import parser.constants as constants


def sub_block_name(block: CFGBlock, sub_block_idx: int) -> str:
    return f"{block.block_id}_{sub_block_idx}"


def initialize_sub_blocks(initial_block: CFGBlock, sub_blocks_instrs: List[Tuple[List[CFGInstruction], bool]]) -> List[CFGBlock]:
    """
    Given the initial block and the instructions that form the corresponding sub-blocks, generates a
    CFG block for each sub-block and updates the jump and output stack information from these blocks
    """
    cfg_sub_blocks = []
    comes_from = initial_block.get_comes_from()

    for sub_block_idx, (sub_block_instrs, split_instruction_sub_block) in enumerate(sub_blocks_instrs):
        new_sub_block_idx = sub_block_name(initial_block, sub_block_idx)

        # Determine the jump type according to whether it is a initial block or a call to a function
        if sub_block_idx != len(sub_blocks_instrs) - 1:
            # Current sub block does not correspond to the last one
            new_sub_block_type = "split_instruction_block" if split_instruction_sub_block else "sub_block"
        else:
            new_sub_block_type = initial_block.get_jump_type()

        new_cfg_sub_block = CFGBlock(new_sub_block_idx, sub_block_instrs, new_sub_block_type,
                                     initial_block.assignment_dict)

        new_cfg_sub_block.process_function_calls(initial_block.function_calls)

        # We need to update the comes from value
        for block_id in comes_from:
            new_cfg_sub_block.add_comes_from(block_id)

        cfg_sub_blocks.append(new_cfg_sub_block)
        comes_from = [new_sub_block_idx]

    # After generating the sequence of sub blocks, we need to update the jumps to and falls to connect the sub blocks
    # and the final stack values
    current_falls_to = initial_block.get_falls_to()
    current_jumps_to = initial_block.get_jump_to()

    for cfg_sub_block in reversed(cfg_sub_blocks):

        # All the blocks except the last one fall into this category
        if cfg_sub_block.get_jump_type() == "split_instruction_block":
            # The last values of the stack corresponds to the values introduced by the final value
            current_stack_values = cfg_sub_block.get_instructions_to_compute()[-1].get_out_args()
            # Initially we keep the stack elements from the original block
        else:
            current_stack_values = initial_block.final_stack_elements

        cfg_sub_block.set_falls_to(current_falls_to)
        cfg_sub_block.set_jump_to(current_jumps_to)
        cfg_sub_block.final_stack_elements = current_stack_values
        
        current_falls_to = cfg_sub_block.block_id
        current_jumps_to = None

    return cfg_sub_blocks


def update_edges_cfg(new_block_list: CFGBlockList, modified_blocks: Dict[str, Tuple[str, str]]) -> None:
    """
    Updates the edges (jumps, falls and comes from) in the cfg block list using the information of the modified
    blocks (previous name: (name of the first sub-block, name of the last sub-block)
    """
    # We need to update edges among blocks with the new names
    for block_name, cfg_block in new_block_list.blocks.items():

        # First we update jumps to and falls to the first sub block (if split)
        modified_jumps_to = modified_blocks.get(cfg_block.get_jump_to(), None)
        if modified_jumps_to is not None:
            cfg_block.set_jump_to(modified_jumps_to[0])

        modified_falls_to = modified_blocks.get(cfg_block.get_falls_to(), None)
        if modified_falls_to is not None:
            cfg_block.set_falls_to(modified_falls_to[0])

        # For the comes from, we refer to the last sub block
        comes_from = cfg_block.get_comes_from()
        new_comes_from = []
        for previous_block in comes_from:
            modified_previous_block = modified_blocks.get(previous_block, None)
            if modified_previous_block is not None:
                new_comes_from.append(modified_previous_block[1])
            else:
                new_comes_from.append(previous_block)

        cfg_block.set_comes_from(new_comes_from)

    # Finally, we update the initial block
    modified_start_block = modified_blocks.get(new_block_list.start_block, None)
    if modified_start_block is not None:
        new_block_list.start_block = modified_start_block[0]


def compute_sub_block_list(block_list: CFGBlockList) -> CFGBlockList:
    """
    Generates a new CFGBlockList that considers splitting blocks when split instructions are found
    """
    new_block_list = CFGBlockList()
    # For each modified block, we store the names of the initial and final sub block
    modified_blocks = dict()
    for block_name, cfg_block in block_list.blocks.items():
        instructions = cfg_block.get_instructions()

        # Traverse the instructions to determine if there are multiple sub-blocks and whether the block corresponds to
        # a call to a function or an instruction that cannot be processed
        sub_block_instructions: List[Tuple[List[CFGInstruction], bool]] = []
        current_sub_block = []

        for instr in instructions:
            if instr.get_op_name() in itertools.chain(constants.split_block, cfg_block.function_calls, "JUMP", "JUMPI"):
                # Sub blocks contain a split instruction or a function call as the last instruction
                current_sub_block.append(instr)
                sub_block_instructions.append((current_sub_block, True))
                current_sub_block = []
            else:
                current_sub_block.append(instr)

        # Finally, consider the remaining instructions

        if current_sub_block:
            sub_block_instructions.append((current_sub_block, False))

        # If there is at least two sub-blocks, then we need to generate the new blocks
        if len(sub_block_instructions) > 1:
            modified_blocks[block_name] = (sub_block_name(cfg_block, 0),
                                           sub_block_name(cfg_block, len(sub_block_instructions) - 1))

            sub_block_list = initialize_sub_blocks(cfg_block, sub_block_instructions)
            for sub_block in sub_block_list:
                new_block_list.add_block(sub_block)
        else:
            new_block_list.add_block(cfg_block)

    update_edges_cfg(new_block_list, modified_blocks)

    # Finally, we update the initial start block with the new format
    modified_start_block = modified_blocks.get(block_list.start_block, None)
    if modified_start_block is not None:
        new_block_list.start_block = modified_start_block[0]

    return new_block_list


def compute_sub_block_cfg(cfg: CFG) -> CFG:
    """
    Computes the sub blocks to optimize from the CFGs
    """
    new_cfg = deepcopy(cfg)
    new_cfg.modify_cfg_block_list(compute_sub_block_list)
    return new_cfg
