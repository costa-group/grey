"""
Main methods to repairing the stack-too-deep placeholders
"""
from typing import List, Dict, Tuple, Set, Optional, Iterable
from pathlib import Path
import networkx as nx
from collections import Counter

from parser.parser import CFGBlockList, CFGBlock
from greedy.greedy_info import GreedyInfo
from global_params.types import var_id_T, block_id_T, constant_T
from reparation.reachability import construct_reachability
from reparation.insert_placeholders import repair_unreachable
from reparation.tree_scan import TreeScan
from reparation.utils import extract_value_from_pseudo_instr
from graphs.algorithms import information_on_graph


def repair_unreachable_blocklist(cfg_blocklist: CFGBlockList,
                                 elements_to_fix: Counter[var_id_T],
                                 path_to_files: Optional[Path]):
    """
    Assumes the blocks in the cfg contain the information of the
    greedy algorithm according to greedy algorithm
    """
    # TODO: store the dominant tree somewhere it makes sense
    construct_reachability(cfg_blocklist, cfg_blocklist.dominant_tree)
    prepass_fixing_constants(cfg_blocklist, elements_to_fix)

    # Visual debugging information
    if path_to_files is not None:
        reachability_path = path_to_files.joinpath("reachability")
        reachability_path.mkdir(exist_ok=True, parents=True)
        _debug_cfg_reachability(cfg_blocklist, reachability_path)

    phi_webs = repair_unreachable(cfg_blocklist, set(elements_to_fix.keys()))

    if path_to_files is not None:
        repaired = path_to_files.joinpath("repaired_vget")
        repaired.mkdir(exist_ok=True, parents=True)
        _debug_reparation(cfg_blocklist, repaired)

    TreeScan(cfg_blocklist, phi_webs).executable_from_code()


def prepass_fixing_constants(cfg_blocklist: CFGBlockList,
                             elements_to_fix: Counter[var_id_T]):
    """
    We first detect if some of the too-deep computations
    correspond to constants, in which case we can just
    compute them directly in the code without the previous process.
    """
    get_with_constants = _detect_replace_constants(elements_to_fix,
                                                   cfg_blocklist.assigment_dict)

    # Traverse all the blocks
    for block_name, block in cfg_blocklist.blocks.items():
        greedy_info = block.greedy_info

        # Values in the intersection
        if len(get_with_constants.intersection(greedy_info.elements_to_fix)) > 0:
            new_ids = []
            for instr in greedy_info.greedy_ids:
                if instr.startswith("VGET") and (var := extract_value_from_pseudo_instr(instr)) in get_with_constants:
                    constant = cfg_blocklist.assigment_dict[var]
                    new_ids.append(f"PUSH {constant[2:]}")
                else:
                    new_ids.append(instr)

            # We update the greedy ids
            greedy_info.set_greedy_ids(new_ids)


def _detect_replace_constants(elements_to_fix: Counter[var_id_T],
                              assignment_dict: Dict[var_id_T, constant_T]) -> Set[var_id_T]:
    """
    Determines which constants are pushed directly instead of fixed
    """
    constants_to_replace = set()
    for var_, num_uses in elements_to_fix.items():
        # We ignore the variables that are not constants
        if var_ not in assignment_dict:
            continue

        constant = assignment_dict[var_]
        size = (len(constant) - 2) // 2

        # Same heuristic as in the constant propagation
        # uses*size >= #uses + size + 2 for fixing
        if num_uses * size < num_uses + size + 2:
            constants_to_replace.add(var_)

    return constants_to_replace


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
