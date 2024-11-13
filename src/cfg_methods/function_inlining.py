"""
Module to perform function inlining.
"""
import json
from copy import deepcopy, copy
from typing import Set, Dict, Tuple, List
from collections import defaultdict

import networkx as nx

from global_params.types import block_id_T, component_name_T, function_name_T, block_list_id_T, var_id_T
from parser.cfg_block import CFGBlock
from parser.cfg_block_list import CFGBlockList
from parser.cfg_function import CFGFunction
from parser.cfg_object import CFGObject
from parser.cfg import CFG
from cfg_methods.cfg_block_actions.inline_function import InlineFunction
from cfg_methods.variable_renaming import rename_function
from cfg_methods.cost_computation import function2costs_T, compute_gas_bytes

# For each time a function is invoked, we store the position of the instruction (int) in the
# block (blok_id_T) that appears in the block list (block_list_id)
call_info_T = Tuple[int, block_id_T, block_list_id_T]

function2call_info_T = Dict[str, List[call_info_T]]


def inline_functions(cfg: CFG) -> None:
    """
    Inlines the functions that are invoked just in one place
    """
    cfg_object2modify: Dict[component_name_T, function2call_info_T] = generate_function2information(cfg)
    cfg_function2costs = compute_gas_bytes(cfg)

    for object_id, cfg_object in cfg.objectCFG.items():
        inline_functions_cfg_object(cfg_object, cfg_object2modify[object_id], cfg_function2costs[object_id])
        sub_object = cfg.get_subobject()

        if sub_object is not None:
            inline_functions(sub_object)


# Methods to compute the invocation information

def generate_function2information(cfg: CFG) -> Dict[function_name_T, function2call_info_T]:
    """
    For each cfg object, a dictionary is produced that links each function to the position, block and block list
    in which it is used
    """
    function2blocks = dict()
    for object_id, cfg_object in cfg.objectCFG.items():
        current_object2call_info = defaultdict(lambda: [])
        function_names = set(cfg_object.functions.keys())
        generate_function2blocks_block_list(cfg_object.blocks, function_names, current_object2call_info)

        # We also consider the information per function
        for cfg_function in cfg_object.functions.values():
            generate_function2blocks_block_list(cfg_function.blocks, function_names, current_object2call_info)

        function2blocks[object_id] = current_object2call_info
        sub_object = cfg.get_subobject()

        if sub_object is not None:
            function2blocks.update(generate_function2information(sub_object))

    return function2blocks


def generate_function2blocks_block_list(cfg_block_list: CFGBlockList, function_names: Set[function_name_T],
                                        function2blocks: function2call_info_T) -> None:
    """
    Links the function calls that appear in the block list to the exact block and the block list
    """
    for block_name, block in cfg_block_list.blocks.items():
        for i, instruction in enumerate(block.instructions_without_phi_functions()):
            if instruction.get_op_name() in function_names:
                function2blocks[instruction.get_op_name()].append((i, block.block_id, cfg_block_list.name))


# Methods to perform the inlining of cfg objects
def inline_functions_cfg_object(cfg_object: CFGObject, function_call_info: function2call_info_T, 
                                function2costs: function2costs_T):
    # Dict that maps each initial block name in the CFG to the set of blocks in which it can be split
    block2current: Dict[block_id_T, List[block_id_T]] = dict()

    function_call_info, topological_sort = prune_cycles_topological_sort(function_call_info)

    for func_idx, function_name in enumerate(topological_sort):
        call_info = function_call_info[function_name]
        cfg_function = cfg_object.functions[function_name]

        # Only consider blocks for inlining that have just one invocation
        if len(call_info) == 1 or _must_be_inlined(function_name, call_info, function2costs, 
                                                   len(cfg_function.exits)):

            for call_idx, (instr_pos, cfg_block_name, cfg_block_list_name) in enumerate(call_info):
                # print(function_name, cfg_block_list_name)
                cfg_block_list = cfg_object.get_block_list(cfg_block_list_name)

                # Then we determine whether the function has been split
                split_blocks = block2current.get(cfg_block_name, [cfg_block_name])

                # We have to determine the corresponding index if there are multiple blocks
                if len(split_blocks) > 1:
                    split_block_index, position_index = _determine_idx(instr_pos, split_blocks, cfg_block_list)
                else:
                    split_block_index = 0
                    position_index = instr_pos + _adjust_phi_function_idx_misalignment(cfg_block_list.blocks[split_blocks[split_block_index]])

                function_to_inline, renaming_dict = _generate_function_to_inline(cfg_function, func_idx, call_idx, len(call_info))

                # nx.nx_agraph.write_dot(cfg_block_list.to_graph_info(), f"antes.dot")

                inline_action = InlineFunction(position_index, cfg_block_list.blocks[split_blocks[split_block_index]],
                                               cfg_block_list, function_to_inline)

                inline_action.perform_action()

                # nx.nx_agraph.write_dot(cfg_block_list.to_graph_info(), f"despues.dot")

                # Uncomment for validation
                # is_correct, reason = validate_block_list_comes_from(cfg_block_list)

                block2current[cfg_block_name] = split_blocks[:split_block_index] + \
                                                [inline_action.first_sub_block.block_id,
                                                 inline_action.second_sub_block.block_id] + split_blocks[
                                                                                            split_block_index + 1:]
            # As we have decided to inline, we can just remove it from the list of functions
            cfg_object.functions.pop(function_name)


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
        if instr_idx < len(cfg_block.instructions_without_phi_functions()):
            return i, instr_idx + _adjust_phi_function_idx_misalignment(cfg_block)

        # We have to remove an extra instruction, as the previous function calls have been removed
        instr_idx -= len(cfg_block.instructions_without_phi_functions()) + 1
        i += 1
    raise ValueError("Block not found")


def _adjust_phi_function_idx_misalignment(block: CFGBlock) -> int:
    # Here we need to reassign the index considering the preceding phi functions in the block, as
    # we have skipped them
    return len([True for instr in block.get_instructions() if instr.get_op_name() == "PhiFunction"])


def _must_be_inlined(function_name: function_name_T, call_info_list: List[call_info_T], function2costs: function2costs_T,
                     n_function_exits: int):
    """
    Returns whether a function must be inlined or not, according to the call and costs info
    """
    gas_cost, size_cost = function2costs[function_name]

    # "Extra costs" with no inlining: introducing two tags + 2 JUMPDEST + 1 entry jump + multiple exit jumps
    no_inlining_extra_gas = (3 * 3) + 2 * 1 + 3 * (1 + n_function_exits)
    
    # Assuming the tags take 2 bytes
    no_inlining_extra_size = (3 * 3) + 2 * 1 + (1 + n_function_exits) 

    # "Extra costs" with inlining: number of bytes duplicated by number of calls
    inlining_extra_size = size_cost * (len(call_info_list) - 1)
    
    # Decision for whether a function must be inlined or not
    
    # Heuristics: 20 bytes = 1 gas
    # TODO: devise good heuristics for inlining
    return (inlining_extra_size - no_inlining_extra_size) <= 20 * no_inlining_extra_gas


def _generate_function_to_inline(original_function: CFGFunction, func_idx: int, current_call_idx: int,
                                 n_calls: int) -> Tuple[CFGFunction, Dict[block_id_T, block_id_T]]:
    """
    We must rename the blocks when inlining to avoid conflicts, as the function can be inlined multiple times in the
    same function (and hence, the same blocks would appear multiple times). We also return the renaming dict
    """
    # If there is just one call, we avoid renaming the blocks
    if n_calls == 1:
        return original_function, dict()
    # If we are making multiple copies, we copy it call_idx - 1 times, as the last one should remove it
    elif current_call_idx == n_calls - 1:
        copied_function = original_function
    else:
        copied_function = deepcopy(original_function)

    # We have to modify the block list inside the copied function first
    block_list = copied_function.blocks
    renaming_dict = {block_name: f"{block_name}_copy_{current_call_idx}" for block_name in block_list.blocks}
    block_list.rename_blocks(renaming_dict)

    var_ids = _var_ids_from_list(block_list)
    renaming_vars = {var_: f"{var_}_f{func_idx}_{current_call_idx}" for var_ in var_ids}
    renaming_vars.update((var_, f"{var_}_f{func_idx}_{current_call_idx}") for var_ in copied_function.arguments)

    n_renaming_vars = len(renaming_vars)
    rename_function(copied_function, renaming_vars)

    assert n_renaming_vars == len(renaming_vars), \
        "Variable renaming in function duplication should not assign new variables"

    copied_function.exits = [renaming_dict.get(exit_id, exit_id) for exit_id in copied_function.exits]
    copied_function.name = f"{copied_function.name}_copy_{current_call_idx}"
    return copied_function, renaming_dict


# Methods to find a cycle in the call functions, remove them and generate the topological sort

def prune_cycles_topological_sort(function2call_info: function2call_info_T) -> \
        Tuple[function2call_info_T, List[function_name_T]]:
    """
    Given the list of functions invoking one another, we remove the cycles generated (i.e. mutually called functions)
    from the calls and return the topological order
    """
    function_deps = nx.from_dict_of_lists({function_name: [call_info[2] for call_info in call_info_list if call_info[2] in function2call_info]
                                           for function_name, call_info_list in function2call_info.items()},
                                          create_using=nx.DiGraph())
    # We condense the nodes to form a DAG (see https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.components.condensation.html#networkx.algorithms.components.condensation)
    condensed_deps = nx.condensation(function_deps)

    # We compute the topological sort over the original function deps
    component_topological_sort = list(nx.topological_sort(condensed_deps))

    nx.nx_agraph.write_dot(function_deps, "functions.dot")

    # We reverse the change
    original_topological_sort = [original_node for component in component_topological_sort
                                 for original_node in condensed_deps.nodes[component]["members"]]

    # Update the function calls as well using the information from the cycles
    pruned_function2call_info = _prune_cycling_function_calls(function2call_info, [])

    return pruned_function2call_info, original_topological_sort


def _prune_cycling_function_calls(function2call_info: function2call_info_T,
                                  cycle_calls: List[List[function_name_T]]) -> function2call_info_T:
    # TODO: handle this case. A cycle is a closed path were no node is repeated twice, so we can just traverse every
    # two nodes in every list and remove the corresponding edge
    return function2call_info


def _var_ids_from_object(cfg_object: CFGObject) -> Set[var_id_T]:
    var_ids = _var_ids_from_list(cfg_object.blocks)
    for function in cfg_object.functions.values():
        var_ids.update(_var_ids_from_list(function.blocks))
    return var_ids


def _var_ids_from_list(block_list: CFGBlockList) -> Set[var_id_T]:
    var_ids = set()
    for block in block_list.blocks.values():
        for instr in block.get_instructions():
            for arg in [*instr.get_in_args(), *instr.get_out_args()]:
                if not arg.startswith("0x"):
                    var_ids.add(arg)
        cond = block.get_condition()
        if cond is not None:
            if not cond.startswith("0x"):
                var_ids.add(cond)
    return var_ids

