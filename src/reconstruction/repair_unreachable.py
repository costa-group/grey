"""
Module that contains the methods needed to
repair unreachable elements. Notation:

* DUP-SET(a_i, pos): duplicate an element a_i (from position pos)
                     and then store it in a register.

* GET-SET: retrieve an element a_i from memory and then story it elsewhere.
           Needed for unification of the phi-functions. Can be just an empty instruction
           if the variable is introduced in the same position
"""
import networkx as nx
from typing import Set, Tuple, Dict, List, Optional
from collections import Counter
from global_params.types import var_id_T, block_id_T, element_definition_T
from parser.cfg_block_list import CFGBlockList
from greedy.greedy_info import GreedyInfo
from reconstruction.atomic_merged_sets import AtomicMergedSets


def repair_unreachable(block_list: CFGBlockList, greedy_info: Dict[block_id_T, GreedyInfo],
                       dominance_tree: nx.DiGraph, loop_tree: nx.DiGraph, forest_graph: nx.DiGraph,
                       get_count: Counter[var_id_T],
                       elements_to_fix: Set[element_definition_T]) -> Tuple[AtomicMergedSets, Set[element_definition_T]]:
    """
    Repairs unreachable elements in two steps. First, it determines at which 
        
    block_list already contains the instructions generated
    in the greedy algorithm phase.
    """
    atomic_merged_sets, combined_elements_to_fix = fix_inaccessible_phi_values(block_list, greedy_info,
                                                                               get_count, elements_to_fix)

    var2header = variable2block_header(block_list, forest_graph)
    store_stack_elements_block(block_list.start_block, block_list, dominance_tree, greedy_info,
                               get_count, loop_tree, var2header)
    return atomic_merged_sets, combined_elements_to_fix


# Methods for first step: fixing inaccessible phi values

def fix_inaccessible_phi_values(block_list: CFGBlockList,
                                greedy_info: Dict[block_id_T, GreedyInfo],
                                get_count: Counter[var_id_T],
                                elements_to_fix: Set[element_definition_T]) -> Tuple[AtomicMergedSets, Set[element_definition_T]]:
    """
    First pass: introduce the GET-SET and DUP-SET annotations
    for handling phi values. It returns the atomic-merged-sets, which is the
    set of elements that aims to use the same memory resource 
    (although not necessary in practice).
    """
    atomic_merged_sets, color, handled_values = AtomicMergedSets(), 0, set()

    # Extends elements_to_fix with the elements that we iteratively have to fix as well
    combined_elements_to_fix = set()

    for pair_variable_block_id in elements_to_fix:
        pairs_to_traverse = [pair_variable_block_id]
        while pairs_to_traverse:
            add_set = set()
            current_var, current_block_id = pairs_to_traverse.pop()
            combined_elements_to_fix.add((current_var, current_block_id))
            current_block = block_list.get_block(current_block_id)
            phi_instruction = current_block.instruction_from_out(current_var)

            assert phi_instruction.get_op_name() == "PhiInstruction"
            for ai, Bi in zip(phi_instruction.get_in_args(), current_block.entries):
                Bi_greedy_info = greedy_info[Bi]
                if (ai, Bi) not in handled_values:
                    handled_values.add((ai, Bi))
                    num_instructions, dup_pos = Bi_greedy_info.reachable.get(ai, (None, None))

                    # First case: the element is unreachable in all its predecessors,
                    # so we repeat the same process. Hence, it corresponds to a phi_def value
                    if ai in Bi_greedy_info.unreachable:
                        insert_get_set(Bi_greedy_info.greedy_ids, ai, num_instructions)
                        get_count.update(ai)
                        pairs_to_traverse.append((ai, Bi))

                    # Second case: the element can be reached with a dup instruction
                    elif num_instructions is not None:
                        insert_dup_set(Bi_greedy_info.greedy_ids, dup_pos, ai, num_instructions)

                    # Third case: we need to retrieve from another register
                    # (accessible at some point)
                    else:
                        insert_get_set(Bi_greedy_info.greedy_ids, ai, num_instructions)
                        get_count.update(ai)
                        # This is an element to fix, but we don't know exactly
                        # where it should be fixed
                        combined_elements_to_fix.add((ai, None))
                else:
                    # If it has been solved for another situation, we just apply a GET-SET
                    insert_get_set(Bi_greedy_info.greedy_ids, ai, num_instructions)
                    get_count.update(ai)

                    # This is an element to fix, but we don't know exactly
                    # where it should be fixed
                    combined_elements_to_fix.add((ai, None))

                # Update the dup-set
                add_set.add((ai, Bi))

            if add_set:
                atomic_merged_sets.add_set(add_set)

    return atomic_merged_sets, combined_elements_to_fix


def insert_dup_set(instructions: List[str], dup_pos: int, ai: var_id_T, position: int):
    """
    Inserts a DUP-SET to access element ai with a given color. The position from which the dup
    must be done is passed as a parameter as well.
    """
    instructions.insert(position, f"DUP-SET({ai}, {dup_pos + 1})")


def insert_get_set(instructions: List[str], ai: var_id_T, position: int):
    """
    Inserts a GET + SET to access element ai with a given color.
    """
    instructions.insert(position, f"SET({ai})")
    instructions.insert(position, f"GET({ai})")


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
    v_definition_block = var2header[v]

    # Two options: either both of them have the same header or no header at all
    entry_v_definition_block = entry_loop(v_definition_block, loop_tree)
    entry_block_id = entry_loop(block_id, loop_tree)
    return entry_block_id == entry_v_definition_block


# Second Phase: same method

def store_stack_elements_block(current_block_id: block_id_T, block_list: CFGBlockList,
                               dominance_tree: nx.DiGraph,
                               greedy_info: Dict[block_id_T, GreedyInfo],
                               get_counter: Counter[var_id_T],
                               loop_tree: nx.DiGraph,
                               var2header: Dict[var_id_T, block_id_T]) -> Set[var_id_T]:
    """
    Second pass: introduce the DUP-SET instructions that are needed
    for later accessing the corresponding elements according to the
    dominance tree.
    """
    vars_to_introduce = set()

    # Traverse the tree in post-order
    for next_block_id in dominance_tree.successors(current_block_id):
        vars_to_introduce.update(store_stack_elements_block(next_block_id, block_list, dominance_tree,
                                                            greedy_info, get_counter, loop_tree, var2header))

    current_greedy_info = greedy_info[current_block_id]
    final_code = []
    for instruction_id in current_greedy_info.greedy_ids:
        final_code.append(instruction_id)

        # We access the corresponding element
        if instruction_id.startswith("GET"):
            loaded_var = instruction_id[4:-1]
            get_counter.subtract(loaded_var)
            # All gets have been performed
            if get_counter[loaded_var] == 0:
                # We can now consider the corresponding element
                vars_to_introduce.add(loaded_var)

        elif (var_list := current_greedy_info.instr_id2var.get(instruction_id)) is not None:
            # Assuming only one variable can be accessed (can be adapted easily)
            var = var_list[0]
            final_code.append(f"DUP-SET({var})")
            vars_to_introduce.remove(var)

    vars_stored = set()
    reachable_info = current_greedy_info.reachable
    for var in vars_to_introduce.intersection(reachable_info.keys()):
        num_instructions, dup_pos = reachable_info[var]

        if within_loop(var, current_block_id, loop_tree, var2header):
            insert_dup_set(final_code, dup_pos, var, num_instructions)
            vars_stored.add(var)

    # We update the corresponding code
    current_greedy_info.greedy_ids = final_code
    return vars_to_introduce.difference(vars_stored)
