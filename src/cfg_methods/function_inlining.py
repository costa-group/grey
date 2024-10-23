"""
Module to perform function inlining.
"""
from typing import Set, Dict, Tuple, List
from collections import defaultdict
from parser.cfg_block import CFGBlock
from parser.cfg_block_list import CFGBlockList
from parser.cfg import CFG
from parser.cfg_block_actions.inline_function import InlineFunction


def generate_function2blocks(cfg: CFG) -> Dict[str, List[Tuple[int, CFGBlock, CFGBlockList]]]:
    """
    Links each function to the block and block list in which it is used
    """
    function2blocks = dict()
    for object_id, cfg_object in cfg.objectCFG.items():
        function_names = set(cfg_object.functions.keys())
        function2blocks.update(generate_function2blocks_block_list(cfg_object.blocks, function_names))

        # We also consider the information per function
        for cfg_function in cfg_object.functions.values():
            function2blocks.update(generate_function2blocks_block_list(cfg_function.blocks, function_names))

        sub_object = cfg.get_subobject()

        if sub_object is not None:
            function2blocks.update(generate_function2blocks_block_list(cfg_object.blocks, function_names))

    return function2blocks


def generate_function2blocks_block_list(cfg_block_list: CFGBlockList, function_names: Set[str]) -> \
        Dict[str, List[Tuple[int, CFGBlock, CFGBlockList]]]:
    """
    Links the function calls that appear in the block list to the exact block and the block list
    """
    function2blocks = defaultdict(lambda: [])
    for block_name, block in cfg_block_list.blocks.items():
        for i, instruction in enumerate(block.get_instructions()):
            if instruction.get_op_name() in function_names:
                function2blocks[instruction.get_op_name()].append((i, block, cfg_block_list))
    return function2blocks


def inline_functions(cfg: CFG, function2blocks: Dict[str, List[Tuple[int, CFGBlock, CFGBlockList]]]) -> None:
    """
    Inlines the functions that are invoked just in one place
    """
    for object_id, cfg_object in cfg.objectCFG.items():

        # We also consider the information per function
        for function_name, cfg_function in cfg_object.functions.items():
            invocation_list = function2blocks[function_name]
            if len(invocation_list) == 1:
                pos, cfg_block, cfg_block_list = invocation_list[0]
                inline_action = InlineFunction(pos, cfg_block, cfg_block_list, function_name, cfg_object)
                inline_action.perform_action()

        sub_object = cfg.get_subobject()

        if sub_object is not None:
            inline_functions(sub_object, function2blocks)
