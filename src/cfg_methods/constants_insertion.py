"""
Module that inserts an instruction for each constant that appears in the code. There might be several
ways to introduce such instructions if we want to reuse computations across different blocks in the CFG
"""
from typing import Dict, Tuple
from collections import defaultdict
from global_params.types import block_id_T, var_id_T, constant_T
from parser.cfg import CFG
from parser.cfg_function import CFGFunction
from parser.cfg_block_list import CFGBlockList
from parser.cfg_block import CFGBlock
from parser.cfg_instruction import CFGInstruction

# Insertion dict collects all constants that must be assigned a variable for a given block
insertion_dict_T = Dict[block_id_T, Dict[constant_T, var_id_T]]


def insert_variables_for_constants(cfg: CFG) -> None:
    """
    Introduces variables and instructions for constants in the CFG, in order to simplify later stages of the
    stack layout generation. This version introduces the constants just when they are being used
    """
    for object_id, cfg_object in cfg.objectCFG.items():
        constant_counter = 0

        # We insert the variables of the block list in the cfg object
        constants_per_block, constant_counter = insert_variables_for_constants_block_list(cfg_object.blocks,
                                                                                          constant_counter)
        insert_constants_block_list(cfg_object.blocks, constants_per_block)

        for function_name, cfg_function in cfg_object.functions.items():

            # Insert the tags and jumps of the block list
            constants_per_block, constant_counter = insert_variables_for_constants_block_list(cfg_function.blocks,
                                                                                              constant_counter)

            insert_constants_block_list(cfg_function.blocks, constants_per_block)

        sub_object = cfg_object.get_subobject()
        if sub_object is not None:
            insert_variables_for_constants(sub_object)


def insert_variables_for_constants_block_list(cfg_block_list: CFGBlockList, constant_counter: int = 0) -> \
        Tuple[insertion_dict_T, int]:
    """
    Traverse a CFG to annotate which constants must be introduced
    """
    constants_per_block = defaultdict(lambda: dict())

    for block_name, block in cfg_block_list.blocks.items():
        # We must insert constants for phi instructions if they are needed
        for instr in block.get_instructions():
            for in_index, in_arg in enumerate(instr.get_in_args()):

                if in_arg.startswith("0x") and instr.get_op_name()!= "LiteralAssignment":
                    #print(instr.get_op_name())
                    # For constants in phi functions, we need to consider the predecessor in which
                    # the constant was introduced
                    block_to_assign = block.entries[in_index] if instr.get_op_name() == "PhiFunction" else block_name
                    constants_in_block = constants_per_block[block_to_assign]

                    if in_arg not in constants_in_block:
                        constants_in_block[in_arg] = f"c{constant_counter}"
                        constant_counter += 1

    return constants_per_block, constant_counter


def insert_constants_block_list(cfg_block_list: CFGBlockList, constants_per_block: insertion_dict_T) -> None:
    """
    Given the dict that assigns a unique variable for each introduced constant in each block,
    modifies all the blocks in the block_list accordingly.
    """
    for block_name, cfg_block in cfg_block_list.blocks.items():

        #print("*/*/*/**/*/*/*/*/*/*/**/*")
        #print(block_name)
        #print(cfg_block._instructions)
        first_non_phi = None
        for idx, instruction in enumerate(cfg_block.get_instructions()):
            if instruction.get_op_name() == "PhiFunction":
                # Phi functions are handled slightly different, as we have to retrieve the
                # assigned variables from the predecessor blocks
                instruction.in_args = [constants_per_block[predecessor_id].get(in_arg, in_arg)
                                       for in_arg, predecessor_id in zip(instruction.in_args, cfg_block.entries)]

            else:
                # We detect the first non phi instruction, as we are introducing variables in this point
                first_non_phi = idx if first_non_phi is None else first_non_phi
                instruction.in_args = [constants_per_block[cfg_block.block_id].get(in_arg, in_arg)
                                       for in_arg in instruction.in_args]

        # We update by the end of the block if there are no other instructions
        first_non_phi = len(cfg_block.get_instructions()) if first_non_phi is None else first_non_phi

        # Finally, we insert the corresponding instructions
        for constant_value, arg in constants_per_block[cfg_block.block_id].items():
            push_instr = CFGInstruction("push", [], [arg])
            push_instr.literal_args = [constant_value]
            cfg_block.insert_instruction(first_non_phi, push_instr)

        #print(cfg_block._instructions)

