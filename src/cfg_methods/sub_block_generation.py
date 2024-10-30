"""
Module used to generate the CFG representation that is fed into the layout generation and the greedy algorithm
"""
from typing import List, Tuple, Set
import networkx as nx
from global_params.types import block_id_T, function_name_T
from itertools import chain
from parser.cfg_block_list import CFGBlockList
from parser.cfg_block_actions.merge_blocks import MergeBlocks
from parser.cfg import CFG
import parser.constants as constants
from parser.cfg_block_actions.split_block import SplitBlock
from cfg_methods.utils import union_find_search


def split_blocks_cfg(cfg: CFG) -> None:
    """
    Splits the blocks in the cfg
    """
    for object_id, cfg_object in cfg.objectCFG.items():
        modify_block_list_split(cfg_object.blocks)

        # We also consider the information per function
        for function_name, cfg_function in cfg_object.functions.items():
            modify_block_list_split(cfg_function.blocks)

        sub_object = cfg.get_subobject()

        if sub_object is not None:
            split_blocks_cfg(sub_object)


def modify_block_list_split(block_list: CFGBlockList) -> None:
    """
    Modifies a CFGBlockList by splitting blocks when function calls and split instructions are found
    """
    blocks_to_traverse = list(block_list.blocks.items())
    new_start_block = None
    for block_name, cfg_block in blocks_to_traverse:

        # It can be reassigned if the block is split multiple times
        current_block = cfg_block
        instr_idx = 0

        while instr_idx < len(current_block.get_instructions()):
            instr = current_block.get_instructions()[instr_idx]

            is_split_instr = instr.get_op_name() in constants.split_block
            is_function_call = instr.get_op_name() in cfg_block.function_calls

            if is_split_instr or is_function_call:
                # Sub blocks contain a split instruction or a function call as the last instruction
                split_block_action = SplitBlock(instr_idx, current_block, block_list)
                split_block_action.perform_action()

                # Set the first sub block instruction split instruction
                first_sub_block = split_block_action.first_half
                first_sub_block.split_instruction = first_sub_block.get_instructions()[-1]

                # If the current block corresponds to the initial block and we modify it
                if new_start_block is None and current_block.block_id == block_list.start_block:
                    new_start_block = first_sub_block

                current_block = split_block_action.second_half
                instr_idx = 0
            else:
                instr_idx += 1


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

        sub_object = cfg.get_subobject()

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
    nodes_to_merge = _nodes_to_merge(cfg_graph)
    renamed_nodes = dict()
    for first_half_node, second_half_node in nodes_to_merge:
        first_half_updated = union_find_search(first_half_node, renamed_nodes)
        second_half_updated = union_find_search(second_half_node, renamed_nodes)

        first_block = cfg_block_list.get_block(first_half_updated)
        second_block = cfg_block_list.get_block(second_half_updated)

        # Conditions to merge nodes: either they are empty (due to inlining certain functions)
        # or if the first one has no split instruction or calls to functions
        if len(first_block.get_instructions()) == 0 or len(second_block.get_instructions()) == 0 or \
                first_block.get_instructions()[-1].get_op_name() in chain(constants.split_block, function_names):

            nx.nx_agraph.write_dot(cfg_block_list.to_graph(), "antes.dot")

            merge_blocks = MergeBlocks(first_block, second_block, cfg_block_list)
            merge_blocks.perform_action()
            combined_block = merge_blocks.combined_block
            renamed_nodes[first_half_updated] = combined_block.block_id
            renamed_nodes[second_half_updated] = combined_block.block_id

            nx.nx_agraph.write_dot(cfg_block_list.to_graph(), "despues.dot")


def remove_blocks_block_list(cfg_block_list: CFGBlockList) -> None:
    nodes_to_remove = _nodes_to_remove(cfg_block_list.start_block, cfg_block_list.to_graph())
    for node_to_remove in nodes_to_remove:
        cfg_block_list.remove_block(node_to_remove)


def _nodes_to_merge(graph: nx.DiGraph) -> List[Tuple[block_id_T, block_id_T]]:
    """
    From a graph, detects which blocks must be combined
    """
    nodes_to_merge = []
    for node in list(graph.nodes):
        # Check if node has exactly one outgoing edge
        if graph.out_degree(node) == 1:
            # Get the target node
            target = next(graph.successors(node))

            # Check if target node has exactly one incoming edge
            if graph.in_degree(target) == 1:
                nodes_to_merge.append((node, target))
    return nodes_to_merge


def _nodes_to_remove(start_node: block_id_T, graph: nx.DiGraph) -> Set[block_id_T]:
    """
    From a graph, detects which blocks are disconnected from the component of the start node
    """
    return set(graph.nodes.keys()).difference({start_node}.union(nx.descendants(graph, start_node)))
