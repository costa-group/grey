"""
Methods for renaming the variables in the CFG. This is needed because different functions might share
the same variables name, and it interferes the liveness analysis
"""
from typing import Dict, List, Tuple, Set
from global_params.types import var_id_T
from parser.cfg import CFG
from parser.cfg_instruction import CFGInstruction
from parser.cfg_block_list import CFGBlockList
from parser.cfg_function import CFGFunction


def rename_variables_cfg(cfg: CFG) -> None:
    # Store which variable names have been already assigned
    for object_id, cfg_object in cfg.objectCFG.items():
        free_index = 0

        renaming_dict, free_index = renaming_dict_from_instrs(cfg_object.blocks, [], free_index)
        rename_block_list(cfg_object.blocks, renaming_dict)

        # We also consider the information per function
        for cfg_function in cfg_object.functions.values():
            free_index = new_variables_function(cfg_function, free_index)

        sub_object = cfg_object.get_subobject()

        if sub_object is not None:
            rename_variables_cfg(sub_object)


def new_variables_function(cfg_function: CFGFunction, free_index: int) -> int:
    renaming_dict, free_index = renaming_dict_from_instrs(cfg_function.blocks, cfg_function.arguments, free_index)
    cfg_function.arguments = rename_var_list(cfg_function.arguments, renaming_dict)
    rename_block_list(cfg_function.blocks, renaming_dict)
    return free_index


def renaming_dict_from_instrs(block_list: CFGBlockList, input_args: List[var_id_T],
                              free_index: int) -> Tuple[Dict[var_id_T, var_id_T], int]:
    """
    Generates a renaming dict from the output of the instructions, pointing to the next free index
    """
    renaming_dict = dict()
    # Note that input args from functions must be also assigned a new name
    for input_arg in input_args:
        renaming_dict[input_arg] = f"v{free_index}"
        free_index += 1

    for block in block_list.blocks.values():
        for instruction in block.get_instructions():
            for out_arg in instruction.out_args:
                renaming_dict[out_arg] = f"v{free_index}"
                free_index += 1

    return renaming_dict, free_index


def rename_function(cfg_function: CFGFunction, renaming_dict: Dict[var_id_T, var_id_T]) -> None:
    cfg_function.arguments = rename_var_list(cfg_function.arguments, renaming_dict)
    rename_block_list(cfg_function.blocks, renaming_dict)


def rename_block_list(block_list: CFGBlockList, renaming_dict: Dict[var_id_T, var_id_T]) -> None:
    # The renaming dict keeps track of the changes in this block to maintain the coherence
    new_assignment_dict = dict()
    for assigned_variable, constant in block_list.assigment_dict.items():
        new_assignment_dict[renaming_dict.get(assigned_variable, assigned_variable)] = constant
    block_list.assigment_dict = new_assignment_dict

    for block_name, block in block_list.blocks.items():

        for instruction in block.get_instructions():
            rename_vars_in_instr(instruction, renaming_dict)

        if block.get_condition() is not None:
            new_cond_list = rename_var_list([block.get_condition()], renaming_dict)
            block.set_condition(new_cond_list[0])


def rename_vars_in_instr(instruction: CFGInstruction, renaming_dict: Dict[var_id_T, var_id_T]) -> None:
    instruction.out_args = rename_var_list(instruction.out_args, renaming_dict)
    instruction.in_args = rename_var_list(instruction.in_args, renaming_dict)


def rename_var_list(var_list: List[var_id_T], renaming_dict: Dict[var_id_T, var_id_T]) -> List[var_id_T]:
    """
    Only renames the variables that appear in the renaming dict
    """
    updated_var_list = []
    for variable in var_list:
        new_variable_name = renaming_dict.get(variable, None)

        # We ignore constants in the renaming and the already assigned ones are added as is
        if variable.startswith("0x"):
            updated_var_list.append(variable)

        # If it is not None, it means we have already assigned a new name to this variable
        elif new_variable_name is not None:
            updated_var_list.append(new_variable_name)

        else:
            updated_var_list.append(variable)

    return updated_var_list
