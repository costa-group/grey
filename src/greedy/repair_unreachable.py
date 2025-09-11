"""
Module that contains the methods needed to
repair unreachable elements. Notation:

* DUP-SET: duplicate an element a_i and then store it in a register.
* GET-SET: retrieve an element a_i from memory and then story it elsewhere.
           Needed for unification of the phi-functions.
"""
import networkx as nx
from typing import Set, Tuple, Dict, List
from collections import Counter
from global_params.types import var_id_T, block_id_T
from parser.cfg_block import CFGBlock
from parser.cfg_block_list import CFGBlockList
from greedy.greedy_info import GreedyInfo


def repair_unreachable(block_list: CFGBlockList, dominance_tree: nx.DiGraph,
                       get_count: Counter[var_id_T], elements_to_fix: Set[var_id_T])
    """
    Repairs unreachable elements in two steps. First, it determines at which 
        
    block_list already contains the instructions generated
    in the greedy algorithm phase.
    """
    pass


def fix_inaccessible_phi_values(block_list: CFGBlockList,
                                greedy_info: Dict[block_id_T, GreedyInfo],
                                get_count: Counter[var_id_T],
                                elements_to_fix: Set[Tuple[var_id_T, block_id_T]])
    """
    First pass: introduce the GET-SET and DUP-SET annotations
    for handling phi values. It returns the atomic-merged-sets, which is the
    set of elements that aims to use the same memory resource 
    (although not necessary in practice).
    """
    atomic_merged_sets, color, handled_values = [], 0, set()
    for pair_variable_block_id in elements_to_fix:
        pairs_to_traverse = [pair_variable_block_id]
        while pairs_to_traverse:
            add_set = set()
            current_var, current_block_id = pairs_to_traverse.pop()
            current_block = block_list.get_block(current_block_id)
            phi_instruction = current_block.instruction_from_out(current_var)

            assert phi_instruction.get_op_name() == "PhiInstruction"
            for ai, Bi in zip(phi_instruction.get_in_args(), current_block.entries):
                Bi_greedy_info = greedy_info[Bi]
                if (ai, Bi) not in handled_values:
                    handled_values.add((ai, Bi))

                    # First case: the element is unreachable, so we repeate the same process
                    if ai in Bi_greedy_info.unreachable:
                        insert_get_set(Bi_greedy_info.greedy_ids, ai, color)
                        get_count.update(ai)
                        pairs_to_traverse.append((ai, Bi))
                    elif ai in Bi_greedy_info.reachable:
                        insert_dup_set(Bi_greedy_info.greedy_ids, ai, color)
                    else:
                        insert_get_set(Bi_greedy_info.greedy_ids, ai, color)
                        get_count.update(ai)
                else:
                    # If it has been solved for another situation, we just apply a GET-SET
                    insert_get_set(Bi_greedy_info.greedy_ids, ai, color)
                    get_count.update(ai)

                # Update the dup-set
                add_set.add((ai, Bi))

            if add_set:
                atomic_merged_sets.append(add_set)

        # The colour is changed for different phi-function webs
        color = color + 1

    return atomic_merged_sets


def insert_dup_set(instructions: List[str], ai: var_id_T, color: int):
    """
    Inserts a DUP-SET to access element ai with a given color.
    """
    pass


def insert_get_set(instructions: List[str], ai: var_id_T, color: int):
    """
    Inserts a GET-SET to access element ai with a given color.
    """
    pass


def store_stack_elements_block(current_block_id: block_id_T, block_list: CFGBlockList,
                               dominance_tree: nx.DiGraph,
                               greedy_info: Dict[block_id_T, GreedyInfo],
                               get_counter: Counter[var_id_T]) -> Set[var_id_T]:
    """
    Second pass: introduce the DUP-SET instructions that are needed
    for later accessing the corresponding elements according to the
    dominance tree.
    """
    vars_to_introduce = set()
    for next_block_id in dominance_tree.successors(current_block_id):
        vars_to_introduce.update(store_stack_elements_block(next_block_id, block_list, dominance_tree,
                                                            greedy_info, get_counter))
        current_greedy_info = greedy_info[current_block_id]
        for instruction in current_greedy_info.greedy_ids:
            pass

def memory_allocation():
    """
    Final pass: replace the GET and SET instructions by memory
    accesses, considering the atomic-merged-sets aim to go to the same resource.
    """
    pass
