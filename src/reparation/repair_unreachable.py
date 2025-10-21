"""
Main methods to repairing the stack-too-deep placeholders
"""
from typing import List, Dict, Tuple, Set, Optional
from pathlib import Path
import networkx as nx

from parser.parser import CFGBlockList, CFGBlock
from greedy.greedy_info import GreedyInfo
from global_params.types import var_id_T, block_id_T
from reparation.reachability import construct_reachability
from reparation.insert_placeholders import repair_unreachable
from reparation.tree_scan import TreeScan
from graphs.algorithms import information_on_graph


def repair_unreachable_blocklist(cfg_blocklist: CFGBlockList, elements_to_fix: Set[var_id_T],
                                 path_to_files: Optional[Path]):
    """
    Assumes the blocks in the cfg contain the information of the
    greedy algorithm according to greedy algorithm
    """
    # TODO: store the dominant tree somewhere it makes sense
    construct_reachability(cfg_blocklist, cfg_blocklist.dominant_tree)

    # Visual debugging information
    if path_to_files is not None:
        reachability_path = path_to_files.joinpath("reachability")
        reachability_path.mkdir(exist_ok=True, parents=True)
        _debug_cfg_reachability(cfg_blocklist, reachability_path)

    phi_webs = repair_unreachable(cfg_blocklist, elements_to_fix)

    if path_to_files is not None:
        repaired = path_to_files.joinpath("repaired_vget")
        repaired.mkdir(exist_ok=True, parents=True)
        _debug_reparation(cfg_blocklist, repaired)

    TreeScan(cfg_blocklist, phi_webs).executable_from_code()


def _represent_reachability_info(block: CFGBlock, num_elements: int = 5):
    msg = [block.block_id, "Reachable:"]
    greedy_info = block.greedy_info

    # Represent the reachable elements
    current_msg = ["{"]
    for element in greedy_info.reachable:
        if len(current_msg) > num_elements:
            msg.append(' '.join(current_msg))
            current_msg = []
        current_msg.append(element)
    current_msg.append("}")
    msg.append(' '.join(current_msg))
    msg.append("Unreachable:")

    # Represent the unreachable elements
    current_msg = ["{"]
    for element in greedy_info.unreachable:
        if len(current_msg) > num_elements:
            msg.append(' '.join(current_msg))
            current_msg = []
        current_msg.append(element)
    current_msg.append("}")
    msg.append(' '.join(current_msg))

    return '\n'.join(msg)


def _debug_cfg_reachability(cfg_blocklist: CFGBlockList, path_to_files: Path):
    dominant_tree = cfg_blocklist.dominant_tree
    renamed_graph = information_on_graph(dominant_tree,
                                         {block_name: _represent_reachability_info(block)
                                          for block_name, block in cfg_blocklist.blocks.items()})

    nx.nx_agraph.write_dot(renamed_graph, path_to_files.joinpath(f"{cfg_blocklist.name}.dot"))


def _debug_reparation(cfg_blocklist: CFGBlockList, path_to_files: Path):
    cfg_graph = cfg_blocklist.to_graph()
    renamed_graph = information_on_graph(cfg_graph,
                                         {block_name: _represent_greedy_info(block_name, block.greedy_info)
                                          for block_name, block in cfg_blocklist.blocks.items()})

    nx.nx_agraph.write_dot(renamed_graph, path_to_files.joinpath(f"{cfg_blocklist.name}.dot"))


def _represent_greedy_info(block_name: block_id_T, greedy_info: GreedyInfo) -> str:
    return block_name + '\n' + '\n'.join(greedy_info.greedy_ids)
