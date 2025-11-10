"""
Methods for analizing the bytecode in the solution
"""
from pathlib import Path
from collections import Counter
from typing import Set, Dict, List
from parser.cfg import CFG, CFGObject, CFGBlockList
from global_params.types import function_name_T


def function_frequency(cfg: CFG) -> List[Dict]:
    """
    For each cfg object, a dictionary is produced that links each function to the position, block and block list
    in which it is used
    """
    function2info = Counter()
    current_info = []
    for object_id, cfg_object in cfg.objectCFG.items():
        function_names = set(cfg_object.functions.keys())
        generate_function2blocks_block_list(cfg_object.blocks, function_names, function2info)

        # We also consider the information per function
        for cfg_function in cfg_object.functions.values():
            generate_function2blocks_block_list(cfg_function.blocks, function_names, function2info)

        current_info.append({"object": object_id, "num_functions": len(function_names),
                             "num_calls": sum(function2info.values())})

        sub_object = cfg_object.get_subobject()
        if sub_object is not None:
            current_info.extend(function_frequency(sub_object))

    return current_info


def generate_function2blocks_block_list(cfg_block_list: CFGBlockList, function_names: Set[function_name_T],
                                        function2blocks: Dict[function_name_T, int]) -> None:
    """
    Links the function calls that appear in the block list to the exact block and the block list
    """
    for block_name, block in cfg_block_list.blocks.items():
        for i, instruction in enumerate(block.instructions_without_phi_functions()):
            if instruction.get_op_name() in function_names:
                function2blocks.update([cfg_block_list.name])
