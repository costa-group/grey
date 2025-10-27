"""
Methods for computing the reachability of the stack vars
from symbolic execution of the stack + greedy ids
"""
import copy
import networkx as nx
from typing import List, Dict, Tuple, Set, Optional, Iterable
from analysis.symbolic_execution import execute_instr_id
from global_params.types import var_id_T, instr_id_T, instr_JSON_T, block_id_T
from parser.cfg_block_list import CFGBlockList
from parser.cfg_instruction import CFGInstruction
from reparation.utils import extract_value_from_pseudo_instr

MAX_STACK_SIZE = 16

# TODO: efficient way to compute reachability
#  depending on the concrete instruction


def update_reachable(stack: List[var_id_T], instr_idx: int,
                     reachability_dict: Dict[var_id_T, Tuple[int, int, bool]],
                     is_last: bool, forbidden_elements: Set[var_id_T]) -> Dict[var_id_T, Tuple[int, int, bool]]:
    for i, elem in enumerate(stack[:MAX_STACK_SIZE]):
        if elem not in forbidden_elements:
            reachability_dict[elem] = (i, instr_idx, is_last)
    return reachability_dict


def reachability_from_greedy(greedy_ids: List[instr_id_T],
                             initial_stack: List[var_id_T],
                             user_instrs: List[instr_JSON_T],
                             split_instruction_call: Optional[CFGInstruction] = None):
    """
    Produces the reachability of a block with the greedy ids and the split instruction
    """
    forbidden_elements = set()
    num_instr = 0
    reachable = update_reachable(initial_stack, num_instr, {}, len(greedy_ids) == 0, forbidden_elements)
    # We execute instruction in the greedy

    for instr in greedy_ids:
        num_instr += 1
        execute_instr_id(instr, initial_stack, user_instrs)

        # For instructions with VGET, we don't consider
        # the reachability after they have accessed
        if instr.startswith("VGET"):
            get_value = extract_value_from_pseudo_instr(instr)
            forbidden_elements.add(get_value)

        # Condition for last: split_instruction_call is None and
        # it is the last index
        update_reachable(initial_stack, num_instr, reachable,
                         split_instruction_call is None and num_instr == len(greedy_ids), forbidden_elements)

    # We also have to execute the split instruction just in case
    # it produces a value that can be accessed (only for functions)
    if split_instruction_call is not None:
        # Consuming elements
        num_instr += 1
        initial_stack = split_instruction_call.out_args + initial_stack[len(split_instruction_call.in_args):]
        update_reachable(initial_stack, num_instr, reachable, True, forbidden_elements)

    return reachable


def block_unreachability(reachable: Iterable[var_id_T], previous_unreachable: Set[var_id_T],
                         live_in: Set[var_id_T], live_out: Set[var_id_T]):
    """
    Given the sets, determine which elements are unreachable
    """
    return ((previous_unreachable.intersection(live_in)).union(live_out)).difference(reachable)


def construct_reachability_block(block_name: block_id_T, cfg_blocklist: CFGBlockList,
                                 dominant_tree: nx.DiGraph, previous_unreachable: Set[var_id_T]):
    block = cfg_blocklist.get_block(block_name)
    greedy_info = block.greedy_info

    spec = copy.deepcopy(block.spec)
    reachable = reachability_from_greedy(greedy_info.greedy_ids, spec["src_ws"],
                                         greedy_info.user_instrs,
                                         block.split_instruction if block.get_jump_type() == "sub_block" else None)

    unreachable = block_unreachability(reachable.keys(), previous_unreachable,
                                       block.liveness["in"], block.liveness["out"])

    # Assign the information
    greedy_info.reachable = reachable
    greedy_info.unreachable = unreachable

    for successor in dominant_tree.successors(block_name):
        construct_reachability_block(successor, cfg_blocklist, dominant_tree, unreachable)


def construct_reachability(cfg_blocklist: CFGBlockList, dominance_tree: nx.DiGraph) -> None:
    """
    Computes the reachability of all blocks and stores the information in the
    corresponding field in GreedyInfo
    """
    construct_reachability_block(cfg_blocklist.start_block, cfg_blocklist, dominance_tree, set())
