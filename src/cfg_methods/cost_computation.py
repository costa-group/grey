"""
Module to compute an estimation on the gas and bytes-in-size spent. Useful for determining whether a function must
be inlined or not
"""
import numpy as np
from typing import Dict, Tuple, Set
from global_params.types import function_name_T, var_id_T, component_name_T
from parser.cfg import CFG
from parser.cfg_function import CFGFunction
from parser.cfg_block_list import CFGBlockList
from parser.cfg_block import CFGBlock
from parser.utils_parser import get_push_number_hex

# Type of the cost we are interested on studying: gas and size costs
costs_T = Tuple[int, int]

# Type of the dict that maps each function name to an estimation on its gas and size costs
function2costs_T = Dict[function_name_T, costs_T]


def compute_gas_bytes(cfg: CFG) -> Dict[component_name_T, function2costs_T]:
    """
    Estimates the gas and size costs of all the function inside the CFG structure
    """
    function2costs = dict()
    for object_id, cfg_object in cfg.objectCFG.items():
        current_object2costs = dict()

        # We also consider the information per function
        for function_name in cfg_object.functions:
            compute_gas_bytes_function(function_name, cfg_object.functions, current_object2costs, set())

        function2costs[object_id] = current_object2costs
        sub_object = cfg.get_subobject()

        if sub_object is not None:
            function2costs.update(compute_gas_bytes(sub_object))

    return function2costs


def compute_gas_bytes_function(function_name: function_name_T, function_dict: Dict[function_name_T, CFGFunction],
                               function2costs: function2costs_T, traversed_functions: Set[function_name_T]) -> costs_T:
    function_costs = function2costs.get(function_name, None)
    if function_costs is not None:
        return function_costs

    # We have to be careful of recursive functions. If we encounter a function that has already been
    # traversed, we set the gas cost to infinite (i.e it cannot be inlined)
    if function_name in traversed_functions:
        function2costs[function_name] = np.inf, 1
        return np.inf, 1

    traversed_functions.add(function_name)

    # We need to keep track of which values are introduced and consumed, as we can count how many times they must
    # be duplicated. Initially, we have the elements passed as input
    previously_introduced = set(function_dict[function_name].get_arguments())

    gas_cost, size_cost = compute_gas_bytes_block_list(function_dict[function_name].blocks, function_dict,
                                                       function2costs, previously_introduced, traversed_functions)
    function2costs[function_name] = gas_cost, size_cost
    return gas_cost, size_cost


def compute_gas_bytes_block_list(cfg_block_list: CFGBlockList, function_dict: Dict[function_name_T, CFGFunction],
                                 function2costs: function2costs_T, previously_introduced: Set[var_id_T],
                                 traversed_functions: Set[function_name_T]) -> costs_T:
    gas_cost, size_cost = 0, 0

    for block in cfg_block_list.blocks.values():
        block_gas, block_size = compute_gas_bytes_block(block, function_dict, function2costs, previously_introduced,
                                                        traversed_functions)
        gas_cost += block_gas
        size_cost += block_size
    return gas_cost, size_cost


def compute_gas_bytes_block(block: CFGBlock, function_dict: Dict[function_name_T, CFGFunction],
                            function2costs: function2costs_T, previously_introduced: Set[var_id_T],
                            traversed_functions: Set[function_name_T]) -> costs_T:
    gas_cost, size_cost = 0, 0
    for instruction in block.get_instructions():

        # First we consider the case in which the function has already been computed
        if instruction.get_op_name() in function2costs.keys():
            op_gas_cost, op_size_cost = function2costs[instruction.get_op_name()]

        # First we account the cost of the op name
        elif instruction.get_op_name() in function_dict.keys():
            op_gas_cost, op_size_cost = compute_gas_bytes_function(instruction.get_op_name(), function_dict,
                                                                   function2costs, traversed_functions)

        else:
            op_gas_cost, op_size_cost = instruction.gas_spent_op, instruction.bytes_required

        gas_cost += op_gas_cost
        size_cost += op_size_cost

        # Then we consider that every argument must be either duplicated or pushed (for constants)
        # TODO: think more carefully if we can make some assumptions
        for in_value in instruction.get_in_args():
            if in_value.startswith("0x"):
                # PUSH0 case
                gas_cost += 2 if in_value == "0x00" else 3
                size_cost += 1 if in_value == "0x00" else (1 + get_push_number_hex(in_value))
            elif in_value in previously_introduced:
                previously_introduced.remove(in_value)
            else:
                # Account for a DUPx
                gas_cost += 3
                size_cost += 1

        for out_value in instruction.get_out_args():
            previously_introduced.add(out_value)

    return gas_cost, size_cost
