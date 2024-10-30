"""
Methods for renaming the variables in the CFG. This is needed because different functions might share
the same variables name, and it interferes the liveness analysis
"""
from typing import Dict, List, Tuple, Set
from global_params.types import var_id_T
from parser.cfg import CFG
from parser.cfg_instruction import CFGInstruction
from parser.cfg_block_list import CFGBlockList


def rename_variables_cfg(cfg: CFG) -> None:
    # Store which variable names have been already assigned
    already_assigned = set()
    free_index = 0
    for object_id, cfg_object in cfg.objectCFG.items():
        free_index = rename_variables_block_list(cfg_object.blocks, already_assigned, free_index)

        # We also consider the information per function
        for cfg_function in cfg_object.functions.values():
            free_index = rename_variables_block_list(cfg_function.blocks, already_assigned, free_index)

        sub_object = cfg.get_subobject()

        if sub_object is not None:
            rename_variables_cfg(sub_object)


def rename_variables_block_list(block_list: CFGBlockList, variables_assigned: Set[var_id_T], free_index: int) -> int:
    # The renaming dict keeps track of the changes in this block to maintain the coherence
    renaming_dict = dict()
    for block_name, block in block_list.blocks.items():
        for instruction in block.get_instructions():
            free_index = modify_vars_in_instr(instruction, variables_assigned, renaming_dict, free_index)
    return free_index


def modify_vars_in_instr(instruction: CFGInstruction, variables_assigned: Set[var_id_T],
                         renaming_dict: Dict[var_id_T, var_id_T], free_index: int) -> int:
    instruction.in_args, free_index = modified_var_list(instruction.in_args, variables_assigned,
                                                        renaming_dict, free_index)
    instruction.out_args, free_index = modified_var_list(instruction.out_args, variables_assigned,
                                                         renaming_dict, free_index)
    return free_index


def modified_var_list(var_list: List[var_id_T], variables_assigned: Set[var_id_T], renaming_dict: Dict[var_id_T, var_id_T],
                      free_index: int) -> Tuple[List[var_id_T], int]:
    updated_var_list = []
    for variable in var_list:
        new_variable_name = renaming_dict.get(variable, None)

        # We ignore constants in the renaming
        if variable.startswith("0x"):
            updated_var_list.append(variable)

        # If it is not None, it means we have already assigned a new name to this variable
        elif new_variable_name is not None:
            updated_var_list.append(new_variable_name)

        # Repeated name from another variable. We have to assign a new name
        elif variable in variables_assigned:
            new_variable_name = f"v{free_index}"
            renaming_dict[variable] = new_variable_name
            variables_assigned.add(variable)
            updated_var_list.append(new_variable_name)
            free_index += 1

        # The variable name is available. We just update the free index to ensure no overlapping is possible
        else:
            free_index = max(free_index, int(variable[1:]) + 1)
            variables_assigned.add(variable)
            updated_var_list.append(variable)

    return updated_var_list, free_index
