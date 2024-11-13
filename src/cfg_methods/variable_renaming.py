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
        already_assigned = set()
        free_index = 0

        free_index = rename_variables_block_list(cfg_object.blocks, already_assigned, dict(), free_index)

        # We also consider the information per function
        for cfg_function in cfg_object.functions.values():
            free_index = rename_cfg_function(cfg_function, already_assigned, dict(), free_index)

        sub_object = cfg.get_subobject()

        if sub_object is not None:
            rename_variables_cfg(sub_object)


def rename_cfg_function(cfg_function: CFGFunction, assigned_global: Set[var_id_T],
                         renaming_dict: Dict[var_id_T, var_id_T], free_index: int, generate_next: bool = True) -> int:
    cfg_function.arguments, free_index = modified_var_list(cfg_function.arguments, assigned_global,
                                                           renaming_dict, free_index)
    free_index = rename_variables_block_list(cfg_function.blocks, assigned_global, renaming_dict, free_index, generate_next)
    return free_index


def rename_variables_block_list(block_list: CFGBlockList, variables_assigned: Set[var_id_T],
                                renaming_dict: Dict[var_id_T, var_id_T], free_index: int, generate_next: bool = True) -> int:
    # The renaming dict keeps track of the changes in this block to maintain the coherence
    for block_name, block in block_list.blocks.items():

        for instruction in block.get_instructions():
            free_index = modify_vars_in_instr(instruction, variables_assigned, renaming_dict, free_index, generate_next)

        if block.get_condition() is not None:
            new_cond_list, free_index = modified_var_list([block.get_condition()], variables_assigned,
                                                          renaming_dict, free_index, generate_next)
            block.set_condition(new_cond_list[0])
    # We have to update the names with the ones that have already been assigned
    variables_assigned.update(renaming_dict.values())
    return free_index


def modify_vars_in_instr(instruction: CFGInstruction, assigned_global: Set[var_id_T],
                         renaming_dict: Dict[var_id_T, var_id_T], free_index: int, generate_next: bool = True) -> int:
    instruction.out_args, free_index = modified_var_list(instruction.out_args, assigned_global,
                                                         renaming_dict, free_index, generate_next)
    instruction.in_args, free_index = modified_var_list(instruction.in_args, assigned_global,
                                                        renaming_dict, free_index, generate_next)
    return free_index


def modified_var_list(var_list: List[var_id_T], assigned_global: Set[var_id_T],
                      renaming_dict: Dict[var_id_T, var_id_T], free_index: int, generate_next: bool = True) -> Tuple[List[var_id_T], int]:
    updated_var_list = []
    for variable in var_list:
        new_variable_name = renaming_dict.get(variable, None)

        # We ignore constants in the renaming and the already assigned ones are added as is
        if variable.startswith("0x"):
            updated_var_list.append(variable)

        # If it is not None, it means we have already assigned a new name to this variable
        elif new_variable_name is not None:
            updated_var_list.append(new_variable_name)

        # If it has already been assigned
        elif variable in assigned_global:
            assert generate_next, "The renaming shouldn't introduce new elements"
            new_variable_name = f"v{free_index}"
            renaming_dict[variable] = new_variable_name
            updated_var_list.append(new_variable_name)
            free_index += 1

        # Last case: first time we encounter this value in the block list
        else:
            if generate_next:
                free_index = max(free_index, int(variable[1:]) + 1)
            renaming_dict[variable] = variable
            updated_var_list.append(variable)

    return updated_var_list, free_index


# Methods for renaming just using a dict

def rename_function(cfg_function: CFGFunction, renaming_dict: Dict[var_id_T, var_id_T]) -> None:
    cfg_function.arguments = rename_var_list(cfg_function.arguments, renaming_dict)
    rename_block_list(cfg_function.blocks, renaming_dict)


def rename_block_list(block_list: CFGBlockList, renaming_dict: Dict[var_id_T, var_id_T]) -> None:
    # The renaming dict keeps track of the changes in this block to maintain the coherence
    for block_name, block in block_list.blocks.items():

        for instruction in block.get_instructions():
            rename_vars_in_instr(instruction, renaming_dict)

        if block.get_condition() is not None:
            new_cond_list = rename_var_list([block.get_condition()], renaming_dict)
            block.set_condition(new_cond_list[0])
        block.final_stack_elements = rename_var_list(block.final_stack_elements, renaming_dict)


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
