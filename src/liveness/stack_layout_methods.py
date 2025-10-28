"""
Module that contains the methods to generate stack layouts from the liveness information.
"""
import collections
from typing import Dict, List, Set, Tuple, Counter
import networkx as nx
from itertools import zip_longest

from global_params.types import var_id_T, block_id_T
from parser.cfg_block_list import CFGBlockList
from parser.cfg_instruction import CFGInstruction
from liveness.liveness_analysis import LivenessAnalysisInfoSSA
from liveness.utils import trim_none, combine_lists_with_order, combine_lists_with_junk

def compute_variable_depth(liveness_info: Dict[str, LivenessAnalysisInfoSSA], topological_order: List) -> Dict[
    str, Dict[str, Tuple[int, int, int]]]:
    """
    For each variable at every point in the CFG, returns the corresponding depth of the last time a variable was used
    and the position being used in the current block (if any). Useful for determining in which order
    variables are placed in a layout
    TODO: improve the efficiency
    """
    variable_depth_out = dict()
    variable_depth_in = dict()
    max_depth = len(topological_order) + 1
    max_instr_idx = 100

    for node in reversed(topological_order):
        block_info = liveness_info[node].block_info
        instructions = block_info.instructions

        current_variable_depth_out = dict()

        # Initialize variables in the live_in set to len(topological_order) + 1
        for input_variable in liveness_info[node].out_state.live_vars:
            current_variable_depth_out[input_variable] = max_depth, max_instr_idx, max_instr_idx

        # For each successor, compute the variable depth information and update the corresponding map
        for succ_node in block_info.successors:

            # The succesor node might not be analyzed yet if there is a cycle. We just ignore it,
            # as we will visit it later
            previous_variable_depth = variable_depth_in.get(succ_node, dict())

            for variable, previous_variable_info in previous_variable_depth.items():
                # Update the depth if it already appears in the dict
                variable_info = current_variable_depth_out.get(variable, None)
                if variable_info is not None:
                    # If the depth of the successor variable is less than the one we have actually
                    if variable_info > previous_variable_info:
                        current_variable_depth_out[variable] = previous_variable_info[0] + 1, previous_variable_info[1], previous_variable_info[2]
                else:
                    current_variable_depth_out[variable] = previous_variable_info[0] + 1, previous_variable_info[1], previous_variable_info[2]

        # Afterwards, we update the information of the in set
        current_variable_depth_in = current_variable_depth_out.copy()

        # Link each variable to the position being used in the instructions
        for i, instruction in enumerate(instructions):
            for j, in_arg in enumerate(instruction.in_args):
                current_variable_depth_in[in_arg] = 0, i, j

        variable_depth_out[node] = current_variable_depth_out
        variable_depth_in[node] = current_variable_depth_in

    return variable_depth_in


def compute_block_level(dominance_tree: nx.DiGraph, start: str) -> Dict[str, int]:
    """
    Computes the block level according to the dominance tree
    """
    return nx.shortest_path_length(dominance_tree, start)


def unification_block_dict(block_list: CFGBlockList) -> Dict[block_id_T, Tuple[block_id_T, List[block_id_T], List[CFGInstruction]]]:
    """
    Given the CFG, it finds those blocks that must unify their corresponding output stacks, due to jumping to the same
    block and the corresponding phi instructions
    """
    unification_dict = dict()
    for block_name, block in block_list.blocks.items():
        comes_from = block.get_comes_from()

        # Comes from can have more than two blocks
        if len(comes_from) > 1:

            info_to_store = block_name, block.entries if block.entries else comes_from, block.phi_instructions()
            # If current block has a Phi Instruction, it uses the order determined by the entries field
            for predecessor_block in comes_from:
                unification_dict[predecessor_block] = info_to_store

    return unification_dict


def output_stack_layout(input_stack: List[str], final_stack_elements: List[str],
                        live_vars: Set[str], variable_depth_info: Dict[str, Tuple],
                        can_have_junk: bool) -> Tuple[List[str], int]:
    """
    Generates the output stack layout before and after the last instruction
    (i.e. the one not optimized by the greedy algorithm), according to the variables
    in live vars, the variables that must appear at the top of the stack and the information from the input stack
    """

    # We keep the variables in the input stack in the same order if they appear in the variable vars (so that we
    # don't need to move them elsewhere). It might contain None variables if the corresponding variables are consumed
    # Variables can appear repeated in the input stack due to splitting in several instructions. Hence, we just want
    # to keep a copy of each variable, the one that is deepest in the stack.
    reversed_stack_relative_order = []
    already_introduced = set()
    for var_ in reversed(input_stack):
        if var_ in live_vars and var_ not in already_introduced:
            reversed_stack_relative_order.append(var_)
            already_introduced.add(var_)
        else:
            reversed_stack_relative_order.append(None)

    # We undo the reversed traversal skipping the first None elements
    bottom_output_stack, num_nones = trim_none(list(reversed(reversed_stack_relative_order)))

    vars_to_place = live_vars.difference(set(final_stack_elements + bottom_output_stack))

    # Sort the vars to place according to the variable depth info order in reversed order
    vars_to_place_sorted = sorted(vars_to_place, key=lambda x: (variable_depth_info.get(x, (-1, )), x))

    # First case: there are more elements than gaps. Hence, we keep the
    # same order
    if len(vars_to_place_sorted) >= num_nones:
        bottom_output_stack = combine_lists_with_order(bottom_output_stack, vars_to_place_sorted)
        # No junk is generated
        junk_idx = len(bottom_output_stack)

    # Second case: there are more gaps. We might resurface part of the stack
    # to avoid shuffling too much in between
    else:
        bottom_output_stack, junk_size = combine_lists_with_junk(bottom_output_stack, vars_to_place_sorted,
                                                                 can_have_junk)

        junk_idx = len(bottom_output_stack)

        # We have to add the part of the input stack that is junk
        if junk_size > 0:
            bottom_output_stack = bottom_output_stack + input_stack[-junk_size:]

    # The final stack elements must appear in the top of the stack
    return final_stack_elements + bottom_output_stack, junk_idx + len(final_stack_elements)


def max_tail_head_overlap(lst1, lst2, live):
    """
    Finds the max overlap between the head and the tail
    """
    n, m = len(lst1), len(lst2)
    overlap_len = 0

    # Start from the longest possible overlap and move forward
    for i in range(1, min(n, m) + 1):
        # We stop when we find a live variable
        if lst2[i-1] in live:
            break
        if lst1[-i:] == lst2[:i]:  # Compare only once per step
            overlap_len = i  # Update the max overlap found

    return overlap_len


def propagate_output_stack(input_stack: List[str], final_stack_elements: List[str],
                           live_vars: Set[str], variable_depth_info: Dict[str, int],
                           split_instruction_in_args: List[str]) -> List[str]:
    """
    Similar to output_stack_layout, but the heuristics is to preserve the stack as is and just add the new information
    """
    bottom_output_stack = input_stack
    vars_to_place = live_vars.difference(set(final_stack_elements + bottom_output_stack))

    # Sort the vars to place according to the variable depth info order in reversed order
    vars_to_place_sorted = sorted(vars_to_place, key=lambda x: (variable_depth_info[x], x), reverse=True)

    # We add the variables to be placed in order
    bottom_output_stack = list(reversed(vars_to_place_sorted)) + bottom_output_stack

    # Special case: we can reuse the bottom output stack for the split instruction arguments
    if final_stack_elements == [] and len(vars_to_place_sorted) == 0:
        overlap = max_tail_head_overlap(split_instruction_in_args, bottom_output_stack, live_vars)
    else:
        overlap = 0
    # The final stack elements must appear in the top of the stack
    return final_stack_elements + bottom_output_stack[overlap:]


def generate_phi_func(target_block_id: block_id_T, predecessor_blocks: List[block_id_T],
                      live_vars_dict: Dict[block_id_T, Set[var_id_T]], phi_functions: List[CFGInstruction]):
    # TODO: uses the input stacks for all the brother stacks for a better combination
    # First we extract the information from the phi functions. For each predecessor block, we generate a dict
    # that maps each variable with each input arg. These nested dicts are important because we want to link the
    # variables that are linked to each predecessor block
    phi_func = collections.defaultdict(lambda: {})
    for phi_function in phi_functions:
        for input_arg, predecessor_block in zip(phi_function.in_args, predecessor_blocks):
            phi_func[predecessor_block][phi_function.out_args[0]] = input_arg

    # The variables that appear in some of the liveness set of the variables but not in the successor must be
    # accounted as well. In order to do so, we introduce some kind of "PhiFunction" that combines these values
    # in the resulting block

    # First we identify these variables, removing the variables that are already part of a phi functions of that block.
    # We want to remove variables related to the phi functions of the considered block,as there can be values in
    # some phi functions that affect other blocks (see an explanation in explanations/23_01_unify_stack_brothers)
    variables_to_remove = {predecessor_block: live_vars_dict[predecessor_block].difference(
        live_vars_dict[target_block_id].union(phi_func.get(predecessor_block, {}).values()))
        for predecessor_block in predecessor_blocks}

    # Then we combine them as new phi functions. We fill with bottom values if there are not enought values to combine
    pseudo_phi_functions = {f"b{i}": in_args for i, in_args in
                            enumerate(zip_longest(*(variables_to_remove[predecessor_block]
                                                    for predecessor_block in predecessor_blocks),
                                                  fillvalue="bottom"))}
    for out_arg, in_args in pseudo_phi_functions.items():
        for input_arg, predecessor_block in zip(in_args, predecessor_blocks):
            # We must consider that the phi function might not have assigned a value to phi_func[predecessor_block]
            if phi_func.get(predecessor_block, None) is None:
                phi_func[predecessor_block] = dict()
            phi_func[predecessor_block][out_arg] = input_arg

    return phi_func, pseudo_phi_functions.keys()


def unify_stack_joint(predecessor_id: var_id_T, combined_output_stack: List[var_id_T],
                      phi_func: Dict[block_id_T, Dict[var_id_T, var_id_T]],
                      live_vars: Set[var_id_T]) -> List[var_id_T]:
    predecessor_output_stack = []
    # The argument corresponds to the input of a phi function
    # We need to access two dicts
    phi_funcs_pred = phi_func.get(predecessor_id, None)

    # Three possibilities:
    for out_var in combined_output_stack:

        # First case: The variable corresponds to a Phi Function
        # See test/repeated_live_vars
        in_arg = phi_funcs_pred.get(out_var, None) if phi_funcs_pred is not None else None

        # THIS MUST BE THE FIRST CASE.
        # See test/* for an example on why it has to be like this
        # TODO: generate test from semanticTests/inlineAssembly_inline_assembly_for2
        #  and why we must first check the phi functions
        if in_arg is not None:
            predecessor_output_stack.append(in_arg)

        # Second case: the variable is already live
        else:
            predecessor_output_stack.append(out_var)

            # Otherwise, we have to introduce a bottom value
    return predecessor_output_stack


def propagate_input_to_joint(input_stack: List[var_id_T], phi_use2phi_def: Dict[var_id_T, var_id_T],
                             live_vars: Set[var_id_T]) -> List[var_id_T]:
    placeholder_stack = []
    already_introduced = set()
    # We traverse the elements in reversed order in case they are no longer used
    for var_ in reversed(input_stack):
        # First case: the variable is live, so we keep it in the same order
        if var_ in live_vars and var_ not in already_introduced:
            placeholder_stack.append(var_)
            already_introduced.add(var_)

        # Second phase: the variable is used in a phi-function
        elif (phi_def := phi_use2phi_def.get(var_)) and phi_def not in already_introduced:
            already_introduced.add(phi_def)

        # Third case: it will be removed: so we don't care about its concrete value:
        else:
            placeholder_stack.append(var_)

    return list(reversed(placeholder_stack))


def generate_combined_block_from_original(original_in_stack: List[var_id_T],
                                          live_vars_target: Set[var_id_T],
                                          phi_func_original: Dict[var_id_T, var_id_T]):

    combined_in = []
    already_added = set()
    for var_ in reversed(original_in_stack):
        # If var_ is live and not added yet, place in the same position
        if var_ in live_vars_target:
            combined_in.append(var_)
            already_added.add(var_)
            continue

        # If var_ corresponds to value used in a phi_function,
        # then we replace it with phi_def (as it will be propagated
        # backwards accordingly)
        propagated_value = next((out_var for out_var, in_var in phi_func_original.items()
                                 if in_var == var_ and out_var not in already_added), None)
        if propagated_value is not None:
            combined_in.append(propagated_value)
            already_added.add(propagated_value)
        # Otherwise, we introduce the initial variable
        else:
            combined_in.append(var_)
    return list(reversed(combined_in))


def unify_stacks_brothers(target_block_id: block_id_T, predecessor_blocks: List[block_id_T],
                          live_vars_dict: Dict[block_id_T, Set[var_id_T]], phi_functions: List[CFGInstruction],
                          variable_depth_info: Dict[str, Tuple], original_block: block_id_T,
                          original_in_stack: List[var_id_T], can_have_junk: bool) -> Tuple[List[block_id_T], Dict[block_id_T, List[var_id_T]]]:
    """
    Generate the output stack for all blocks that share a common block destination and the consolidated stack,
    considering the PhiFunctions
    """
    phi_func, introduced_phis = generate_phi_func(target_block_id, predecessor_blocks, live_vars_dict, phi_functions)

    live_vars_with_pseudo_phi = live_vars_dict[target_block_id].union(introduced_phis)

    # We update the initial stack of the predecessor
    # so that the combined output stack considers this information
    combined_init_stack = generate_combined_block_from_original(original_in_stack, live_vars_with_pseudo_phi,
                                                                phi_func[original_block])

    # We generate the input stack of the combined information, considering the pseudo phi functions
    combined_output_stack, junk_idx = output_stack_layout(combined_init_stack, [], live_vars_with_pseudo_phi,
                                                          dict(variable_depth_info, **{key: (0,) for key in introduced_phis}), can_have_junk)

    # Reconstruct all the output stacks
    predecessor_output_stacks = dict()

    # We unify the combined stack with all the other blocks
    for predecessor_id in predecessor_blocks:

        predecessor_stack = unify_stack_joint(predecessor_id, combined_output_stack,
                                              phi_func, live_vars_dict[predecessor_id])

        # The only one that goes with junk corresponds to the original block
        # we have used
        # We unify non junk elements
        if predecessor_id == original_block:
            predecessor_output_stacks[predecessor_id] = predecessor_stack
        else:
            predecessor_output_stacks[predecessor_id] = predecessor_stack[:junk_idx]

    return combined_output_stack[:junk_idx], predecessor_output_stacks


def unify_stacks_dominant(target_block_id: block_id_T, predecessor_blocks: List[block_id_T],
                          live_vars_dict: Dict[block_id_T, Set[var_id_T]],
                          phi_functions: List[CFGInstruction], variable_depth_info: Dict[str, Tuple],
                          original_block: block_id_T, original_in_stack: List[var_id_T],
                          can_have_junk: bool) -> Tuple[List[block_id_T], Dict[block_id_T, List[var_id_T]], Set[var_id_T]]:
    """
    Generate the output stack for two blocks such that the original block dominates the other block.
    In this case, we preserve the stack as is to avoid introducing bottoms in between, possibly
    modifying the liveness that connect the target block with the original block with the target through
    the second path
    """
    phi_func, introduced_phis = generate_phi_func(target_block_id, predecessor_blocks, live_vars_dict, phi_functions)

    # INVARIANT: The original block is the one with no bottom values,
    # as it is the one that has ALL the values
    assert all(phi_value != "bottom" for phi_value in phi_func[original_block].values()), \
        f"We assumed the original block had no bottom value in the combined phi, but {phi_func[original_block]}"

    values_to_propagate = set()
    for block in phi_func:
        if block != original_block:
            for target_var in phi_func[block]:
                if phi_func[block][target_var] == "bottom":
                    phi_func[block][target_var] = phi_func[original_block][target_var]
                    values_to_propagate.add(phi_func[original_block][target_var])

    live_vars_with_pseudo_phi = live_vars_dict[target_block_id].union(introduced_phis)

    # We update the initial stack of the predecessor
    # so that the combined output stack considers this information
    combined_init_stack = generate_combined_block_from_original(original_in_stack, live_vars_with_pseudo_phi,
                                                                phi_func[original_block])

    # We generate the input stack of the combined information, considering the pseudo phi functions
    combined_output_stack, junk_idx = output_stack_layout(combined_init_stack, [], live_vars_with_pseudo_phi,
                                                          dict(variable_depth_info, **{key: (0,) for key in introduced_phis}), can_have_junk)

    # Reconstruct all the output stacks
    predecessor_output_stacks = dict()

    # We unify the combined stack with all the other blocks
    for predecessor_id in predecessor_blocks:

        predecessor_stack = unify_stack_joint(predecessor_id, combined_output_stack,
                                              phi_func, live_vars_dict[predecessor_id])

        # The only one that goes with junk corresponds to the original block
        # we have used
        # We unify non junk elements
        if predecessor_id == original_block:
            predecessor_output_stacks[predecessor_id] = predecessor_stack
        else:
            predecessor_output_stacks[predecessor_id] = predecessor_stack[:junk_idx]

    return combined_output_stack[:junk_idx], predecessor_output_stacks, values_to_propagate



def joined_stack(combined_output_stack: List[str], live_vars: Set[str]):
    """
    Detects which elements must be bottom in the joined stack from several predecessor blocks. In order to
    do so, it assigns to 'bottom' the values that are not in the live-in set
    """
    return [stack_element if stack_element in live_vars else "bottom" for stack_element in combined_output_stack]


def forget_values(input_stack: List[var_id_T], live_vars: Set[var_id_T]) -> List[var_id_T]:
    """
    Removes the deepest values from the input stack if they are no longer live.
    """
    i = len(input_stack) - 1
    while i >= 0 and input_stack[i] not in live_vars:
        i -= 1
    return input_stack[:i+1]
