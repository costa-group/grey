"""
Module used to generate the CFG representation that is fed into the layout generation and the greedy algorithm
"""
import itertools
from typing import List, Tuple, Set, Dict
import networkx as nx
from global_params.types import block_id_T, function_name_T, cfg_object_T
from itertools import chain
from parser.cfg_block_list import CFGBlockList
from cfg_methods.cfg_block_actions.merge_blocks import MergeBlocks
from parser.cfg import CFG
from parser.cfg_instruction import CFGInstruction
import parser.constants as constants
from cfg_methods.cfg_block_actions.split_block import SplitBlock
from cfg_methods.utils import union_find_search
from cfg_methods.jump_insertion import tag_from_tag_dict


def split_blocks_cfg(cfg: CFG, tags_object: Dict[cfg_object_T, Dict[block_id_T, int]]) -> None:
    """
    Splits the blocks in the cfg (identifying the split instructions) and updates the tags dict accordingly
    """
    for object_id, cfg_object in cfg.objectCFG.items():
        tag_dict = tags_object[object_id]
        function2tag = {}
        for function_name, function in cfg_object.functions.items():
            # We obtain the tag from the initial block (generate a new one)
            start_block_tag = tag_from_tag_dict(function.blocks.start_block, tag_dict)
            function2tag[function_name] = start_block_tag

        modify_block_list_split(cfg_object.blocks, function2tag, tag_dict)

        # We also consider the information per function
        for function_name, cfg_function in cfg_object.functions.items():
            modify_block_list_split(cfg_function.blocks, function2tag, tag_dict)

        sub_object = cfg_object.get_subobject()

        if sub_object is not None:
            split_blocks_cfg(sub_object, tags_object)


def modify_block_list_split(block_list: CFGBlockList, function2tag: Dict[function_name_T, int],
                            tag_dict: Dict[block_id_T, int]) -> None:
    """
    Modifies a CFGBlockList by splitting blocks when function calls and split instructions are found
    """
    blocks_to_traverse = list(block_list.blocks.items())
    new_start_block = None
    for block_name, cfg_block in blocks_to_traverse:

        # It can be reassigned if the block is split multiple times
        current_block = cfg_block
        instr_idx = 0

        if block_name == "modifier_mod1_Block8_split_0":
            pass

        # We cannot split the last instruction, as it would result in an empty block
        while instr_idx < len(current_block.get_instructions()) - 1:
            instr = current_block.get_instructions()[instr_idx]

            is_split_instr = instr.get_op_name() in constants.split_block
            is_function_call = instr.get_op_name() in function2tag

            if is_split_instr or is_function_call:
                # Sub blocks contain a split instruction or a function call as the last instruction
                split_block_action = SplitBlock(instr_idx, current_block, block_list)
                split_block_action.perform_action()

                # Set the first sub block instruction split instruction
                first_sub_block = split_block_action.first_half
                first_sub_block.split_instruction = instr

                # If the current block corresponds to the initial block and we modify it
                if new_start_block is None and current_block.block_id == block_list.start_block:
                    new_start_block = first_sub_block

                # We need to update the tag dict with the previous value. We have to be careful
                # because there might be several tags
                if current_block.block_id in tag_dict:
                    tag_value = tag_dict.pop(current_block.block_id)
                    tag_dict[first_sub_block.block_id] = tag_value

                current_block = split_block_action.second_half
                instr_idx = 0

                # Finally, we need to introduce the PUSH [tag] values in a function call
                if is_function_call:
                    # Add a new tag for current block
                    second_half_tag = str(tag_from_tag_dict(current_block.block_id, tag_dict))
                    function_call_tag = str(function2tag[instr.get_op_name()])

                    i = 0
                    # Phi instructions must always come first
                    while i < len(first_sub_block.get_instructions()) and \
                            first_sub_block.get_instructions()[i].get_op_name() == "PhiFunction":
                        i += 1

                    # In the first half, introduce both the target and returning tags
                    first_sub_block.insert_instruction(i, CFGInstruction("PUSH [tag]", [], [second_half_tag]))
                    first_sub_block.insert_instruction(i, CFGInstruction("PUSH [tag]", [], [function_call_tag]))

                    # The split instruction of the first sub block must contain the tags
                    instr.in_args = [function_call_tag] + instr.in_args + [second_half_tag]

            else:
                instr_idx += 1

        # Nevertheless, we check if the last instruction is a split one and set it
        last_instr = current_block.get_instructions()[-1] if len(current_block.get_instructions()) > 0 else None
        if last_instr is not None:

            # First case: function call. We have to introduce the jumps to invoke the function.
            # If this is the last instruction, it means we don't need to jump back, as there is no function return.
            # We only jump to the function
            # See example: strings_unicode_string/unicode_string_standard_input.json
            tag_function = function2tag.get(last_instr.get_op_name(), None)
            if tag_function is not None:

                # Again, we need to skip the phi functions for inserting the jump tag
                i = 0
                while i < len(current_block.get_instructions()) and \
                        current_block.get_instructions()[i].get_op_name() == "PhiFunction":
                    i += 1

                current_block.insert_instruction(i, CFGInstruction("PUSH [tag]", [], [str(tag_function)]))

                if len(current_block.successors) > 0:
                    # If there is a sucessor, it is an uncondicional jump
                    assert len(current_block.successors) == 1, "Function call with successors " \
                                                               "must correspond to an unconditional JUMP"
                    next_tag = str(tag_from_tag_dict(current_block.successors[0], tag_dict))
                    current_block.insert_instruction(i, CFGInstruction("PUSH [tag]", [], [next_tag]))
                    values_before_in_args = [next_tag]
                else:
                    values_before_in_args = []
                # We update the in args accordingly
                last_instr.in_args = [str(tag_function)] + last_instr.in_args + values_before_in_args

                # The function call is still the split instruction
                current_block.split_instruction = last_instr

            # Other split instructions: we set the last instruction as a split instruction
            elif last_instr.get_op_name() in itertools.chain(constants.split_block, ["JUMP", "JUMPI"],
                                                             constants.terminal_ops):
                current_block.split_instruction = last_instr


# Methods for generating the CFG graph after the inlining and identifying the sub-blocks

def combine_remove_blocks_cfg(cfg: CFG):
    """
    Combines the blocks that have just one inside and outside nodes.
    Moreover, removes the blocks that are disconnected due to unnecessary splits
    """
    for object_id, cfg_object in cfg.objectCFG.items():
        function_names = list(cfg_object.functions.keys())
        combine_remove_blocks_block_list(cfg_object.blocks, function_names)

        # We also consider the information per function
        for function_name, cfg_function in cfg_object.functions.items():
            combine_remove_blocks_block_list(cfg_function.blocks, function_names)

        sub_object = cfg_object.get_subobject()

        if sub_object is not None:
            combine_remove_blocks_cfg(sub_object)


def combine_remove_blocks_block_list(cfg_block_list: CFGBlockList, function_names: List[function_name_T]):
    """
    Simplifies the representation of the block list by combining and removing unnecessary nodes in the CFG.
    These blocks are the result of inlining functions
    """
    combine_blocks_block_list(cfg_block_list, function_names)
    remove_blocks_block_list(cfg_block_list)


def combine_blocks_block_list(cfg_block_list: CFGBlockList, function_names: List[function_name_T]) -> None:
    """
    Updates both the blocks in the cfg block list and the cfg graph by combining empty blocks
    and blocks with no split instruction
    """
    cfg_graph = cfg_block_list.to_graph()
    nodes_to_merge = _nodes_to_merge(cfg_graph, cfg_block_list, function_names)
    renamed_nodes = dict()
    for first_half_node, second_half_node in nodes_to_merge:
        first_half_updated = union_find_search(first_half_node, renamed_nodes)
        second_half_updated = union_find_search(second_half_node, renamed_nodes)

        first_block = cfg_block_list.get_block(first_half_updated)
        second_block = cfg_block_list.get_block(second_half_updated)

        # Conditions to merge nodes: either they are empty (due to inlining certain functions)
        # or if the first one has no split instruction or calls to functions
        # nx.nx_agraph.write_dot(cfg_block_list.to_graph(), "before.dot")

        merge_blocks = MergeBlocks(first_block, second_block, cfg_block_list)
        merge_blocks.perform_action()
        combined_block = merge_blocks.combined_block
        renamed_nodes[first_half_updated] = combined_block.block_id
        renamed_nodes[second_half_updated] = combined_block.block_id

        # nx.nx_agraph.write_dot(cfg_block_list.to_graph(), "after.dot")


def remove_blocks_block_list(cfg_block_list: CFGBlockList) -> None:
    nodes_to_remove = _nodes_to_remove(cfg_block_list.start_block, cfg_block_list.to_graph())
    for node_to_remove in nodes_to_remove:
        cfg_block_list.remove_block(node_to_remove)


def _nodes_to_merge(graph: nx.DiGraph, block_list: CFGBlockList,
                    function_names: List[function_name_T]) -> List[Tuple[block_id_T, block_id_T]]:
    """
    From a graph, detects which blocks must be combined
    """
    nodes_to_merge = []
    for node in list(graph.nodes):

        # Check if node has exactly one outgoing edge
        if graph.out_degree(node) == 1:
            # Get the target node
            target = next(graph.successors(node))

            first_block = block_list.get_block(node)
            second_block = block_list.get_block(target)

            # Condition: target node has exactly one incoming edge and they can be merged safely
            if graph.in_degree(target) == 1 and (len(first_block.get_instructions()) == 0 or
                                                 len(second_block.get_instructions()) == 0 or
                                                 first_block.get_instructions()[-1].get_op_name()
                                                 not in chain(constants.split_block, function_names,
                                                              ["JUMP", "JUMPI"])):
                nodes_to_merge.append((node, target))
    return nodes_to_merge


def _nodes_to_remove(start_node: block_id_T, graph: nx.DiGraph) -> Set[block_id_T]:
    """
    From a graph, detects which blocks are disconnected from the component of the start node
    """
    return set(graph.nodes.keys()).difference({start_node}.union(nx.descendants(graph, start_node)))
