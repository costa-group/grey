"""
Module that contains the methods needed to
repair unreachable elements. Notation:

* DUP-SET(a_i, pos): duplicate an element a_i (from position pos)
                     and then store it in a register.

* GET-SET: retrieve an element a_i from memory and then story it elsewhere.
           Needed for unification of the phi-functions. Can be just an empty instruction
           if the variable is introduced in the same position
"""
from collections import Counter
from typing import Set, Tuple, Dict, List, Optional

import networkx as nx

from global_params.types import var_id_T, block_id_T
from greedy.greedy_info import GreedyInfo
from parser.cfg_block_list import CFGBlockList
from reparation.phi_webs import PhiWebs


def repair_unreachable(block_list: CFGBlockList, elements_to_fix: Set[var_id_T]) -> PhiWebs:
    """
    Repairs unreachable elements in two steps. First, it determines at which
    block_list already contains the instructions generated
    in the greedy algorithm phase.
    """
    phi_def2block = compute_phi_def2block(block_list)

    # The phi elements to fix are those that are unreachable in their definition
    # TODO: Check it is indeed the case
    phi_elements_to_fix = set(element for element in elements_to_fix
                              if (block_def := phi_def2block.get(element)) is not None
                              and element in block_list.get_block(block_def).greedy_info.unreachable)

    atomic_merged_sets = fix_inaccessible_phi_values(block_list, phi_elements_to_fix, phi_def2block)

    var2header = variable2block_header(block_list, block_list.loop_nesting_forest)
    store_stack_elements_tree(block_list, var2header)
    return atomic_merged_sets


# Phi value to block in which it is defined
def compute_phi_def2block(cfg_block_list: CFGBlockList) -> Dict[var_id_T, block_id_T]:
    return {out_var: block_id for block_id, block in cfg_block_list.blocks.items()
            for instruction in block.phi_instructions()
            for out_var in instruction.get_out_args()}


# Methods for first step: fixing inaccessible phi values

def fix_inaccessible_phi_values(block_list: CFGBlockList,
                                phi_elements_to_fix: Set[var_id_T],
                                phi_def2block: Dict[var_id_T, block_id_T]) -> PhiWebs:
    """
    First pass: introduce the GET-SET and DUP-SET annotations
    for handling phi values. It returns the atomic-merged-sets, which is the
    set of elements that aims to use the same memory resource 
    (although not necessary in practice).
    """
    atomic_merged_sets, color, handled_values = PhiWebs(), 0, set()

    for element in phi_elements_to_fix:
        definition = phi_def2block[element]

        pairs_to_traverse = [(element, definition)]

        while pairs_to_traverse:
            add_set = set()
            current_var, current_block_id = pairs_to_traverse.pop()
            handled_values.add(current_var)
            current_block = block_list.get_block(current_block_id)
            phi_instruction = current_block.instruction_from_out(current_var)

            assert phi_instruction.get_op_name() == "PhiInstruction"
            for ai, Bi in zip(phi_instruction.get_in_args(), current_block.entries):
                Bi_greedy_info = block_list.get_block(Bi).greedy_info

                # We iterate if the value is unreachable
                # (i.e it can be reached at no point)
                if ai in Bi_greedy_info.unreachable and ai not in handled_values:
                    B_def = phi_def2block[ai]
                    # We need to find in which block ai is
                    # defined to perform the same process (if needed)
                    pairs_to_traverse.append((ai, B_def))

                # For all cases, we need to add a virtual copy
                Bi_greedy_info.add_virtual_copy(ai)

                add_set.add(ai)

            atomic_merged_sets.join_phi(current_var, add_set)

    return atomic_merged_sets


def process_dup_set(instructions: List[str], dup_pos: int, ai: var_id_T, position: int):
    """
    Inserts a DUP-SET to access element ai with a given color. The position from which the dup
    must be done is passed as a parameter as well.
    """
    instructions.insert(position, f"DUP-VSET({ai}, {dup_pos + 1})")


# Second phase: decide when values are stored using a STORE instruction
# Auxiliary methods

def variable2block_header(cfg_block_list: CFGBlockList, forest_graph: nx.DiGraph) -> Dict[var_id_T, block_id_T]:
    """
    Builds a dictionary that which is the loop header of the outer loop in which the variable
    is defined. Useful for determining when we want to store the variable
    """
    var2header = dict()
    # We only consider blocks that appear as part of the forest graph
    for block_id in forest_graph.nodes:
        block = cfg_block_list.get_block(block_id)

        predecessors = list(forest_graph.predecessors(block_id))
        if len(predecessors) != 0:
            assert len(predecessors) == 1, "There can only be one predecessor in the forest graph"
            predecessor = predecessors[0]

            # We only consider the variables defined in the block
            # Thanks to SSA, they are defined only once
            for variable in block.declared_variables:
                # We link the variable with the block
                var2header[variable] = predecessor
    return var2header


def entry_loop(block_id: block_id_T, loop_tree: nx.DiGraph) -> Optional[var_id_T]:
    """
    Given a block and the loop tree, determines the block that is the header
    of the corresponding loop (if any). Otherwise, returns None
    """
    if block_id in loop_tree:
        # First case: it is already a header because it has multiple successors
        if loop_tree.succ[block_id]:
            return block_id
        # Second case: just return the direct predecessor
        # It is unique
        for predecessor in loop_tree.predecessors(block_id):
            return predecessor
    return None


def within_loop(v: var_id_T, block_id: block_id_T, loop_tree: nx.DiGraph,
                var2header: Dict[var_id_T, block_id_T]) -> bool:
    """
    Determines whether the point in which variable var v and the block block_id are within the
    same loop scope, according to loop_tree
    """
    v_definition_block = var2header.get(v)

    # If the definition is outside loops, then
    # the block id must be as well
    if v_definition_block is None:
        return block_id not in loop_tree

    # Two options: either both of them have the same header or no header at all
    entry_v_definition_block = entry_loop(v_definition_block, loop_tree)
    entry_block_id = entry_loop(block_id, loop_tree)
    return entry_block_id == entry_v_definition_block


# Second Phase: same method

def substract_zero(left_counter: Counter, right_counter: Counter) -> Set:
    """
    Substract two counters, detecting which elements in the left counter are turned
    to zero and returning them. These elements are also removed from both counters
    """
    zero_elements = set()
    for element, n_repetitions in right_counter.items():
        diff = left_counter[element] - n_repetitions

        if diff == 0:
            zero_elements.add(element)
            # We remove the element from both counters
            left_counter.pop(element)

    # Elements to remove
    for element in zero_elements:
        right_counter.pop(element)

    return zero_elements


def store_stack_elements_tree(block_list: CFGBlockList,
                              var2header: Dict[var_id_T, block_id_T]) -> None:
    # TODO: more efficient
    # Compute the global get_count, considering the information from
    # the new introduced placeholders
    get_count = sum((block.greedy_info.get_count for block in block_list.blocks.values()),
                    Counter())

    # Just invoke the recursive function with the stack block
    store_stack_elements_block(block_list.start_block, block_list,
                               get_count, var2header)


def store_stack_elements_block(current_block_id: block_id_T, block_list: CFGBlockList,
                               initial_get_counter: Counter[var_id_T],
                               var2header: Dict[var_id_T, block_id_T]) -> Tuple[Set[var_id_T], Counter[var_id_T]]:
    """
    Second pass: introduce the DUP-SET instructions that are needed
    for later accessing the corresponding elements according to the
    dominance tree.
    """
    vars_to_introduce = set()
    get_counter_combined = Counter()

    # Traverse the tree in post-order, updating the
    # values to introduce and the number of get occurrences so far
    for next_block_id in block_list.dominant_tree.successors(current_block_id):
        vars_successors, get_counter_succ = store_stack_elements_block(next_block_id, block_list,
                                                                       initial_get_counter, var2header)
        vars_to_introduce.update(vars_successors)
        get_counter_combined += get_counter_succ

    current_greedy_info = block_list.get_block(current_block_id).greedy_info

    # Consumed so far
    get_counter_combined += current_greedy_info.get_count

    # First, we update the variables that are accessed through VGET or VGET-VSET
    # and analyze the values that are 0
    elements_popped = substract_zero(initial_get_counter, get_counter_combined)

    # These elements are now introduced to the set
    vars_to_introduce.update(elements_popped)

    vars_stored = set()
    reachable_info = current_greedy_info.reachable
    for var in vars_to_introduce.intersection(reachable_info.keys()):
        if within_loop(var, current_block_id,
                       block_list.loop_nesting_forest, var2header):
            current_greedy_info.insert_dup_vset(var)
            vars_stored.add(var)

    return vars_to_introduce.difference(vars_stored), get_counter_combined
