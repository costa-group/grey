"""
Module that contains the methods to generate stack layouts from the liveness information.
"""
import collections
from typing import Dict, List, Set, Tuple
import networkx as nx
from itertools import zip_longest

from global_params.types import var_id_T, block_id_T
from parser.cfg_block_list import CFGBlockList
from parser.cfg_instruction import CFGInstruction
from liveness.liveness_analysis import LivenessAnalysisInfoSSA


def unify_stacks(predecessor_stacks: List[List[str]], variable_depth_info: Dict[str, int]) -> List[str]:
    """
    Unifies the given stacks, according to the information already provided in variable depth info
    """
    needed_elements = set(elem for stack in predecessor_stacks for elem in stack)
    max_depth = max(variable_depth_info.values()) + 1 if len(variable_depth_info) > 0 else -1
    pairs = [(variable_depth_info.get(stack_elem, max_depth), stack_elem) for stack_elem in needed_elements]
    return [elem[1] for elem in sorted(pairs)]


def build_acyclic_graph_from_CFG(cfg: nx.DiGraph, initial_node) -> nx.DiGraph:
    """
    Builds an acyclic graph by removing the backedges.
    See https://dl.acm.org/doi/pdf/10.1145/358438.349330
    """
    acyclic_graph = cfg.copy(as_view=False)
    visited, current_path = set(), set()
    remove_backwards_edges(initial_node, visited, current_path, cfg, acyclic_graph)
    return acyclic_graph


def remove_backwards_edges(current_node, visited: Set, current_path: Set, cfg:nx.DiGraph, acyclic_graph: nx.DiGraph):
    """
    DFS traversal to detect backedges and remove them from the acyclic graph
    """
    current_path.add(current_node)
    if current_node not in visited:
        visited.add(current_node)
        for next_node in cfg.successors(current_node):
            if next_node in visited:
                # This corresponds to a backedge, as we are traversing the tree from the initial node
                if next_node in current_path:
                    acyclic_graph.remove_edge(current_node, next_node)

            else:
                remove_backwards_edges(next_node, visited, current_path, cfg, acyclic_graph)

    current_path.remove(current_node)


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
                        live_vars: Set[str], variable_depth_info: Dict[str, int]) -> List[str]:
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

    # We undo the reversed traversal
    bottom_output_stack = list(reversed(reversed_stack_relative_order))

    vars_to_place = live_vars.difference(set(final_stack_elements + bottom_output_stack))

    # Sort the vars to place according to the variable depth info order in reversed order
    vars_to_place_sorted = sorted(vars_to_place, key=lambda x: (variable_depth_info[x], x))

    # Try to place the variables in reversed order
    i, j = 0, 0

    while i < len(bottom_output_stack) and j < len(vars_to_place_sorted):
        if bottom_output_stack[i] is None:
            bottom_output_stack[i] = vars_to_place_sorted[j]
            j += 1
        i += 1

    # First exit condition: all variables have been placed in between. Hence, I have to insert the remaining
    # elements at the beginning
    if i == len(bottom_output_stack):
        bottom_output_stack = list(reversed(vars_to_place_sorted[j:])) + bottom_output_stack

    # Second condition: all variables have been placed in between. There can be some None values in between that
    # must be removed
    else:
        # Place the topmost elements in the gaps
        # Ignore the first Nones
        i = 0
        while i < len(bottom_output_stack) and bottom_output_stack[i] is None:
            i += 1

        bottom_output_stack = bottom_output_stack[i:]
        i = 0
        while i < len(bottom_output_stack):
            if bottom_output_stack[i] is None:
                assert bottom_output_stack[0] is not None
                bottom_output_stack[i] = bottom_output_stack[0]
                bottom_output_stack.pop(0)
            else:
                i += 1

    # The final stack elements must appear in the top of the stack
    return final_stack_elements + bottom_output_stack


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


def unify_stacks_brothers(target_block_id: block_id_T, predecessor_blocks: List[block_id_T],
                          live_vars_dict: Dict[block_id_T, Set[var_id_T]], phi_functions: List[CFGInstruction],
                          variable_depth_info: Dict[str, int]) -> Tuple[
    List[block_id_T], Dict[block_id_T, List[var_id_T]]]:
    """
    Generate the output stack for all blocks that share a common block destination and the consolidated stack,
    considering the PhiFunctions
    """
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
    pseudo_phi_functions = {f"b{i}": in_args for i, in_args in enumerate(zip_longest(*(variables_to_remove[predecessor_block]
                                                                                       for predecessor_block in predecessor_blocks),
                                                                                     fillvalue="bottom"))}
    for out_arg, in_args in pseudo_phi_functions.items():
        for input_arg, predecessor_block in zip(in_args, predecessor_blocks):
            # We must consider that the phi function might not have assigned a value to phi_func[predecessor_block]
            if phi_func.get(predecessor_block, None) is None:
                phi_func[predecessor_block] = dict()
            phi_func[predecessor_block][out_arg] = input_arg

    # We generate the input stack of the combined information, considering the pseudo phi functions
    combined_output_stack = output_stack_layout([], [], live_vars_dict[target_block_id].union(pseudo_phi_functions.keys()),
                                                dict(variable_depth_info, **{key: (0,) for key in pseudo_phi_functions.keys()}))

    # Reconstruct all the output stacks
    predecessor_output_stacks = dict()

    for predecessor_id in predecessor_blocks:
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
            elif out_var in live_vars_dict[predecessor_id]:
                predecessor_output_stack.append(out_var)
            else:
                predecessor_output_stack.append("bottom")
                # Otherwise, we have to introduce a bottom value

        predecessor_output_stacks[predecessor_id] = predecessor_output_stack

    return combined_output_stack, predecessor_output_stacks


def unify_stacks_brothers_missing_values(target_block_id: block_id_T, predecessor_blocks: List[block_id_T],
                                         previous_input_stacks: Dict[block_id_T, List[var_id_T]],
                                         live_vars_dict: Dict[block_id_T, Set[var_id_T]], phi_functions: List[CFGInstruction],
                                         variable_depth_info: Dict[str, int]) -> Tuple[List[block_id_T], Dict[block_id_T, List[var_id_T]]]:
    """
    Generate the output stack for all blocks that share a common block destination and the consolidated stack,
    considering the PhiFunctions. The stack values of the predecessor block that are not part of the target stack
    are placed in the bottom of the stack, and conveniently "forgotten"
    """
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

    # We generate the input stack of the combined information (with no pseudo phi function
    combined_output_stack = output_stack_layout([], [], live_vars_dict[target_block_id], variable_depth_info)

    # Reconstruct all the output stacks
    predecessor_output_stacks = dict()

    for predecessor_id in predecessor_blocks:

        # Initialize the predecessor output stack to the variables to remove, considering they are "forgotten"
        # TODO: see how the heuristics of choosing an order can be affected
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
            elif out_var in live_vars_dict[predecessor_id]:
                predecessor_output_stack.append(out_var)
            else:
                predecessor_output_stack.append("bottom")
                # Otherwise, we have to introduce a bottom value

        # The variables to remove are "forgotten"
        # TODO: see how the heuristics of choosing an order can be affected. Maybe consider this as part of the
        #  heuristics
        pos_dict = {element: i for i, element in enumerate(previous_input_stacks.get(predecessor_id, []))}
        predecessor_output_stack = predecessor_output_stack + sorted(variables_to_remove[predecessor_id],
                                                                     key=lambda x:  (pos_dict.get(x, len(pos_dict)), x))

        predecessor_output_stacks[predecessor_id] = predecessor_output_stack

    return combined_output_stack, predecessor_output_stacks


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
