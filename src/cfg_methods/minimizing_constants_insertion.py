"""
Module that inserts an instruction for each constant that appears in the code. There might be several
ways to introduce such instructions if we want to reuse computations across different blocks in the CFG
"""
from typing import Dict, Tuple, Set
from collections import defaultdict
from global_params.types import block_id_T, var_id_T, constant_T
from parser.cfg import CFG
from parser.cfg_block_list import CFGBlockList
from parser.cfg_block import CFGBlock
from parser.cfg_instruction import CFGInstruction

# Insertion dict collects all constants that must be assigned a variable for a given block
insertion_dict_T = Dict[block_id_T, Set[constant_T]]


def insert_variables_for_constants_propagated(cfg: CFG) -> None:
    """
    Introduces variables and instructions for constants in the CFG, in order to simplify later stages of the
    stack layout generation. This version introduces the constants just when they are being used
    """
    for object_id, cfg_object in cfg.objectCFG.items():
        constant_counter = 0

        # We insert the variables of the block list in the cfg object
        constants_per_block = insert_variables_for_constants_block_list(cfg_object.blocks)
        insert_constants_block_list(cfg_object.blocks, constants_per_block)

        for function_name, cfg_function in cfg_object.functions.items():

            # Insert the tags and jumps of the block list
            constants_per_block = insert_variables_for_constants_block_list(cfg_function.blocks)

            insert_constants_block_list(cfg_function.blocks, constants_per_block)

        sub_object = cfg_object.get_subobject()
        if sub_object is not None:
            insert_variables_for_constants_propagated(sub_object)


def insert_variables_for_constants_block_list(cfg_block_list: CFGBlockList) -> \
        Dict[block_id_T, Set[constant_T]]:
    """
    Traverse a CFG to annotate which constants must be introduced in each block
    """
    constants_per_block = defaultdict(lambda: set())

    for block_name, block in cfg_block_list.blocks.items():
        # We must insert constants for phi instructions if they are needed

        for instr in block.get_instructions():
            for in_index, in_arg in enumerate(instr.get_in_args()):

                if in_arg.startswith("0x") and instr.get_op_name() != "LiteralAssignment":
                    # For constants in phi functions, we need to consider the predecessor in which
                    # the constant was introduced
                    block_to_assign = block.entries[in_index] if instr.get_op_name() == "PhiFunction" else block_name
                    constants_in_block = constants_per_block[block_to_assign]

                    if in_arg not in constants_in_block:
                        constants_in_block.add(in_arg)

    return constants_per_block


def insert_constants_block_list(cfg_block_list: CFGBlockList, constants_per_block: insertion_dict_T) -> None:
    """
    Given the dict that assigns a unique variable for each introduced constant in each block,
    modifies all the blocks in the block_list accordingly.
    """
    insert_constants_block_dominant_preorder(cfg_block_list.start_block, cfg_block_list,
                                             constants_per_block, dict(), 0)


def decide_if_propagated(constant: constant_T):
    return len(constant) > 4


def insert_constants_block_dominant_preorder(block_name: block_id_T, cfg_block_list: CFGBlockList,
                                             constants_per_block: insertion_dict_T,
                                             introduced_so_far: Dict[constant_T, var_id_T],
                                             free_idx: int) -> int:

    # First we detect which elements must be introduced
    cfg_block = cfg_block_list.get_block(block_name)

    # We update by the end of the block if there are no other instructions
    first_non_phi = len(cfg_block.phi_instructions())

    constants_to_introduce = set(constant for constant in constants_per_block[block_name].difference(introduced_so_far.keys())
                                 if decide_if_propagated(constant))

    # The constants we need to add are the ones not added so far
    for constant_value in constants_to_introduce:
        arg = f"c{free_idx}"
        introduced_so_far[constant_value] = arg
        free_idx += 1

        push_instr = CFGInstruction("push", [], [arg])
        push_instr.literal_args = [constant_value]
        cfg_block.insert_instruction(first_non_phi, push_instr)

    # For the constants we need to use, we add the possibility of computing
    # it through push
    # for constant in constants_per_block[block_name]:
    #     if constant in introduced_so_far:
    #         cfg_block.assignment_dict[introduced_so_far[constant]] = constant

    insert_constants_block(cfg_block, introduced_so_far)

    # We traverse the tree in preorder, updating the free index
    for next_block in cfg_block_list.dominant_tree.successors(block_name):
        free_idx = insert_constants_block_dominant_preorder(
            next_block, cfg_block_list, constants_per_block, introduced_so_far, free_idx)

    # Before exiting the block ,we pop the constant values
    for constant_value in constants_to_introduce:
        introduced_so_far.pop(constant_value)

    return free_idx


def insert_constants_block(cfg_block: CFGBlock, constants_per_block: Dict[constant_T, var_id_T]) -> None:
    """
    Inserts constants in a concrete block
    """
    first_non_phi = None
    for idx, instruction in enumerate(cfg_block.get_instructions()):
        if instruction.get_op_name() == "PhiFunction":
            # Phi functions are handled slightly different, as we have to retrieve the
            # assigned variables from the predecessor blocks
            instruction.in_args = [constants_per_block.get(in_arg, in_arg)
                                   for in_arg, predecessor_id in zip(instruction.in_args, cfg_block.entries)]

        elif instruction.get_op_name() != "LiteralAssignment":
            # We detect the first non phi instruction, as we are introducing variables in this point
            first_non_phi = idx if first_non_phi is None else first_non_phi

            instruction.in_args = [constants_per_block.get(in_arg, in_arg)
                                   for in_arg in instruction.in_args]
