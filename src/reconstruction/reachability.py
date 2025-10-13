"""
Methods for computing the reachability of the greedy algorithm
"""
import networkx as nx
from typing import List, Dict, Tuple, Set
from analysis.symbolic_execution import execute_instr_id
from global_params.types import var_id_T, instr_id_T, instr_JSON_T

MAX_STACK_SIZE = 16

# TODO: efficient way to compute reachability
#  depending on the concrete instruction


def update_reachable(stack: List[var_id_T], instr_idx: int,
                     reachability_dict: Dict[var_id_T, Tuple[int, int]]) -> Dict[var_id_T, Tuple[int, int]]:
    for i, elem in enumerate(stack):
        reachability_dict[elem] = (i, instr_idx)
    return reachability_dict


def reachability_from_greedy(greedy_ids: List[instr_id_T],
                             initial_stack: List[var_id_T],
                             user_instrs: List[instr_JSON_T]):
    """
    Produces the reachability of a block with the greedy ids
    """
    num_instr = 0
    reachable = update_reachable(initial_stack, num_instr, {})
    # We execute instruction in the greedy

    for instr in greedy_ids:
        num_instr += 1
        execute_instr_id(instr, initial_stack, user_instrs)
        update_reachable(initial_stack, num_instr, reachable)

    return reachable


def block_unreachability(reachable: Set[var_id_T], previous_unreachable: Set[var_id_T],
                         live_in: Set[var_id_T], live_out: Set[var_id_T]):
    """
    Given the sets, determine which elements are unreachable
    """
    return ((previous_unreachable.intersection(live_in)).union(live_out)).difference(reachable)
