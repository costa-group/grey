"""
Module that generates the layouts that are fed into the superoptimization algorithm.
In this case, we build different heuristics to choose the best layout transformation.
As there are heuristics that can be based on the results of preceeding blocks with the greedy algorithm,
in this module the greedy algorithm itself is invoked
"""
import heapq
import itertools
from typing import Dict, List, Type, Any, Set, Tuple, Optional
import networkx as nx
from pathlib import Path
from itertools import zip_longest

from global_params.types import SMS_T, component_name_T, var_id_T, block_id_T
from parser.cfg import CFG
from parser.cfg_block_list import CFGBlockList
from parser.cfg_block import CFGBlock
from parser.cfg_instruction import CFGInstruction
from parser.utils_parser import shorten_name
from analysis.abstract_state import digraph_from_block_info
from graphs.algorithms import condense_to_dag, information_on_graph
from liveness.liveness_analysis import LivenessAnalysisInfo, construct_analysis_info, \
    perform_liveness_analysis_from_cfg_info
from liveness.utils import functions_inputs_from_components



def unify_stacks(predecessor_stacks: List[List[str]], variable_depth_info: Dict[str, int]) -> List[str]:
    """
    Unifies the given stacks, according to the information already provided in variable depth info
    """
    needed_elements = set(elem for stack in predecessor_stacks for elem in stack)
    max_depth = max(variable_depth_info.values()) + 1 if len(variable_depth_info) > 0 else -1
    pairs = [(variable_depth_info.get(stack_elem, max_depth), stack_elem) for stack_elem in needed_elements]
    return [elem[1] for elem in sorted(pairs)]


def compute_variable_depth(liveness_info: Dict[str, LivenessAnalysisInfo], topological_order: List) -> Dict[
    str, Dict[str, int]]:
    """
    For each variable at every point in the CFG, returns the corresponding depth. Useful for
    determining in which order the blocks can be traversed
    TODO: improve the efficiency
    """
    variable_depth_out = dict()
    variable_depth_in = dict()
    max_depth = len(topological_order) + 1

    for node in reversed(topological_order):
        block_info = liveness_info[node].block_info

        current_variable_depth_out = dict()

        # Initialize variables in the live_in set to len(topological_order) + 1
        for input_variable in liveness_info[node].in_state.live_vars:
            current_variable_depth_out[input_variable] = max_depth

        # For each successor, compute the variable depth information and update the corresponding map
        for succ_node in block_info.successors:

            # The succesor node might not be analyzed yet if there is a cycle. We just ignore it,
            # as we will visit it later
            previous_variable_depth = variable_depth_in.get(succ_node, dict())

            for variable, depth in previous_variable_depth.items():
                # Update the depth if it already appears in the dict
                if variable in current_variable_depth_out:
                    current_variable_depth_out[variable] = min(current_variable_depth_out[variable], depth + 1)
                else:
                    current_variable_depth_out[variable] = depth + 1

        current_variable_depth_in = current_variable_depth_out.copy()

        # Finally, we update the corresponding variables that are defined in the blocks
        for used_variable in set(block_info.uses).union(block_info.phi_uses):
            current_variable_depth_out[used_variable] = 0

        variable_depth_out[node] = current_variable_depth_out
        variable_depth_in[node] = current_variable_depth_in

    return variable_depth_out


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
    vars_to_place_sorted = sorted(vars_to_place, key=lambda x: -variable_depth_info[x])

    # Try to place the variables in reversed order
    i, j = len(bottom_output_stack) - 1, 0

    while i >= 0 and j < len(vars_to_place_sorted):
        if bottom_output_stack[i] is None:
            bottom_output_stack[i] = vars_to_place_sorted[j]
            j += 1
        i -= 1

    # First exit condition: all variables have been placed in between. Hence, I have to insert the remaining
    # elements at the beginning
    if i == -1:
        bottom_output_stack = list(reversed(vars_to_place_sorted[j:])) + bottom_output_stack

    # Second condition: all variables have been placed in between. There can be some None values in between that
    # must be removed
    else:
        bottom_output_stack = [var_ for var_ in bottom_output_stack if var_ is not None]

    # The final stack elements must appear in the top of the stack
    return final_stack_elements + bottom_output_stack


def unify_stacks_brothers(target_block_id: block_id_T, predecessor_blocks: List[block_id_T],
                          live_vars_dict: Dict[block_id_T, Set[var_id_T]], phi_functions: List[CFGInstruction],
                          variable_depth_info: Dict[str, int]) -> Tuple[
    List[block_id_T], Dict[block_id_T, List[var_id_T]]]:
    """
    Generate the output stack for all blocks that share a common block destination and the consolidated stack,
    considering the PhiFunctions
    """
    # TODO: uses the input stacks for all the brother stacks for a better combination
    # First we extract the information from the phi functions
    phi_func = {(phi_function.out_args[0], predecessor_block): input_arg for phi_function in phi_functions
                for input_arg, predecessor_block in zip(phi_function.in_args, predecessor_blocks)}

    # The variables that appear in some of the liveness set of the variables but not in the successor must be
    # accounted as well. In order to do so, we introduce some kind of "PhiFunction" that combines these values
    # in the resulting block

    # First we identify these variables
    variables_to_remove = {predecessor_block: live_vars_dict[predecessor_block].difference(live_vars_dict[target_block_id])
                           for predecessor_block in predecessor_blocks}

    # Then we combine them as new phi functions. We fill with bottom values if there are not enought values to combine
    pseudo_phi_functions = {f"b{i}": in_args for i, in_args in enumerate(zip_longest(*(variables_to_remove[predecessor_block]
                                                                                       for predecessor_block in predecessor_blocks),
                                                                                     fillvalue="bottom"))}
    phi_func.update({(out_arg, predecessor_block): input_arg for out_arg, in_args in pseudo_phi_functions.items()
                     for input_arg, predecessor_block in zip(in_args, predecessor_blocks)})

    # We generate the input stack of the combined information, considering the pseudo phi functions
    combined_output_stack = output_stack_layout([], [], live_vars_dict[target_block_id].union(pseudo_phi_functions.keys()),
                                                dict(variable_depth_info, **{key: 0 for key in pseudo_phi_functions.keys()}))

    # Reconstruct all the output stacks
    predecessor_output_stacks = dict()

    for predecessor_id in predecessor_blocks:
        predecessor_output_stack = []
        # Three possibilities:
        for out_var in combined_output_stack:
            # First case: the variable is already live
            if out_var in live_vars_dict[predecessor_id]:
                predecessor_output_stack.append(out_var)
            else:
                in_arg = phi_func.get((out_var, predecessor_id), None)
                # The argument corresponds to the input of a phi function
                if in_arg is not None:
                    predecessor_output_stack.append(in_arg)
                # Otherwise, we have to introduce a bottom value
                else:
                    predecessor_output_stack.append("bottom")

        predecessor_output_stacks[predecessor_id] = predecessor_output_stack

    return combined_output_stack, predecessor_output_stacks


def joined_stack(combined_output_stack: List[str], live_vars: Set[str]):
    """
    Detects which elements must be bottom in the joined stack from several predecessor blocks. In order to
    do so, it assigns to 'bottom' the values that are not in the live-in set
    """
    return [stack_element if stack_element in live_vars else "bottom" for stack_element in combined_output_stack]


def var_order_repr(block_name: str, var_info: Dict[str, int]):
    """
    Str representation of a block name and the information on variables
    """
    text_format = [f"{block_name}:", *(f"{var_}: {idx}" for var_, idx in var_info.items())]
    return '\n'.join(text_format)


def print_json_instr(instr: Dict[str, Any]) -> str:
    return ', '.join(
        [f"Opcode {instr['disasm']}", f"Input args: {instr['inpt_sk']}", f"Output args: {instr['outpt_sk']}"])


def print_stacks(block_name: str, json_dict: Dict[str, Any]) -> str:
    text_format = [f"{block_name}:", f"Src: {json_dict['src_ws']}", f"Tgt: {json_dict['tgt_ws']}"]
    text_format += [print_json_instr(instr) for instr in json_dict["user_instrs"]]
    return '\n'.join(text_format)


class LayoutGeneration:

    def __init__(self, object_id: str, block_list: CFGBlockList, liveness_info: Dict[str, LivenessAnalysisInfo],
                 function_inputs: Dict[component_name_T, List[var_id_T]], name: Path,
                 cfg_graph: Optional[nx.Graph] = None):
        self._component_id = object_id
        self._block_list = block_list
        self._liveness_info = liveness_info
        self._function_inputs = function_inputs

        if cfg_graph is None:
            self._cfg_graph = digraph_from_block_info(liveness_analysis_state.block_info
                                                      for liveness_analysis_state in liveness_info.values())
        else:
            self._cfg_graph = cfg_graph

        self._start = block_list.start_block

        _tree_dir = name.joinpath("tree")
        _tree_dir.mkdir(exist_ok=True, parents=True)

        immediate_dominators = nx.immediate_dominators(self._cfg_graph, self._start)
        self._dominance_tree = nx.DiGraph([v, u] for u, v in immediate_dominators.items() if u != self._start)
        self._dominance_tree.add_node(self._start)

        nx.nx_agraph.write_dot(self._dominance_tree, _tree_dir.joinpath(f"{object_id}.dot"))
        self._block_order = list(nx.topological_sort(self._dominance_tree))

        self._variable_order = compute_variable_depth(liveness_info, self._block_order)

        renamed_graph = information_on_graph(self._cfg_graph, {name: var_order_repr(name, assignments)
                                                               for name, assignments in self._variable_order.items()})
        _var_dir = name.joinpath("var_order")
        _var_dir.mkdir(exist_ok=True, parents=True)
        nx.nx_agraph.write_dot(renamed_graph, _var_dir.joinpath(f"{object_id}.dot"))

        self._layout_dir = name.joinpath("layouts")
        self._layout_dir.mkdir(exist_ok=True, parents=True)

        # Guess: we need to traverse the code following the dominance tree in topological order
        # This is because in the dominance tree together with the SSA, all the nodes

        self._block_depth = compute_block_level(self._dominance_tree, self._start)
        self._unification_dict = unification_block_dict(block_list)

    def _construct_code_from_block(self, block: CFGBlock, input_stacks: Dict[str, List[str]],
                                   output_stacks: Dict[str, List[str]]):
        """
        Constructs the specification for a given block, according to the input and output stacks
        """
        block_id = block.block_id
        liveness_info = self._liveness_info[block_id]
        comes_from = block.get_comes_from()

        # Computing input stack...
        # The stack from comes_from stacks must be equal
        if comes_from:
            predecessor_stacks = [output_stacks[predecessor] for predecessor in comes_from
                                  if predecessor in output_stacks]

            if len(predecessor_stacks) > 1:
                # At this point, the input stack must have been assigned from the predecessors
                input_stack = input_stacks[block.block_id]
            else:
                input_stack = output_stacks[comes_from[0]]
        else:
            # We introduce the necessary args in the generation of the first output stack layout
            # The stack elements we have to "force" a certain order correspond to the input parameters of
            # the function
            input_stack = self._function_inputs[self._block_list.name]

        input_stacks[block.block_id] = input_stack

        # Computing output stack...
        # If the current block belongs to the unification tuples and a brother block has already been assigned
        # a stack, we need to assign the same stack
        next_block_id, elements_to_unify, phi_instructions = self._unification_dict.get(block_id, (None, [], []))
        output_stack = None

        if len(elements_to_unify) > 1:

            # If one of the brothers was assigned previously, the corresponding id is already assigned as well
            if block_id in output_stacks:
                # We store the output stack from the analysis after commbining
                output_stack = output_stacks[block_id]

            # We need to determine a stack that is the combination of the previous ones
            else:
                # We unify the stacks according the first reached block
                combined_liveness_info = {element_to_unify: self._liveness_info[element_to_unify].out_state.live_vars
                                          for element_to_unify in elements_to_unify}
                combined_liveness_info[next_block_id] = self._liveness_info[next_block_id].in_state.live_vars

                combined_output_stack, output_stacks_unified = unify_stacks_brothers(next_block_id,
                                                                                     elements_to_unify,
                                                                                     combined_liveness_info,
                                                                                     phi_instructions,
                                                                                     self._variable_order[next_block_id])

                # Update the output stacks with the ones generated from the unification
                output_stacks.update(output_stacks_unified)
                output_stack = output_stacks[block_id]

                # The combined output stack is the input stack of the successor
                input_stacks[next_block_id] = combined_output_stack

        if output_stack is None:
            output_stack = output_stack_layout(input_stack, block.final_stack_elements,
                                               liveness_info.out_state.live_vars,
                                               self._variable_order[block_id])
            # We store the output stack in the dict, as we have built a new element
            output_stacks[block_id] = output_stack

        # We build the corresponding specification
        block_json = block.build_spec(input_stack, output_stack)

        return block_json

    def _construct_code_from_block_list(self):
        """
        Naive implementation: just traverse the blocks and generate the src and tgt information according to the liveness
        information. In order to keep the stacks coherent, we traverse them according to the dominance tree
        """
        input_stacks = dict()
        output_stacks = dict()
        traversed = set()
        json_info = dict()

        pending_blocks = []
        heapq.heappush(pending_blocks, (0, 0, self._start))

        while pending_blocks:

            _, real_depth, block_name = heapq.heappop(pending_blocks)

            if block_name in traversed:
                continue

            traversed.add(block_name)

            # Retrieve the block
            current_block = self._block_list.get_block(block_name)

            block_specification = self._construct_code_from_block(current_block, input_stacks,
                                                                  output_stacks)

            json_info[block_name] = block_specification

            successors = [possible_successor for possible_successor in
                          [current_block.get_jump_to(), current_block.get_falls_to()]
                          if possible_successor is not None]

            for successor in successors:
                if successor not in traversed:
                    heapq.heappush(pending_blocks, (self._block_depth[successor], real_depth + 1, successor))

        return json_info

    def build_layout(self):
        """
        Builds the layout of the blocks from the given representation
        """
        json_info = self._construct_code_from_block_list()

        renamed_graph = information_on_graph(self._cfg_graph,
                                             {block_name: print_stacks(block_name, json_info[block_name])
                                              for block_name in
                                              self._block_list.blocks})

        nx.nx_agraph.write_dot(renamed_graph, self._layout_dir.joinpath(f"{self._component_id}.dot"))

        return json_info


def layout_generation_cfg(cfg: CFG, final_dir: Path = Path(".")) -> Dict[str, SMS_T]:
    """
    Returns the information from the liveness analysis and also stores a dot file for each analyzed structure
    in "final_dir"
    """
    cfg_info = construct_analysis_info(cfg)
    component2inputs = functions_inputs_from_components(cfg)
    results = perform_liveness_analysis_from_cfg_info(cfg_info)
    component2block_list = cfg.generate_id2block_list()

    jsons = dict()

    for component_name, liveness in results.items():
        cfg_info_suboject = cfg_info[component_name]["block_info"]
        digraph = digraph_from_block_info(cfg_info_suboject.values())

        short_component_name = shorten_name(component_name)

        layout = LayoutGeneration(component_name, component2block_list[component_name], liveness, component2inputs,
                                  final_dir, digraph)

        layout_blocks = layout.build_layout()
        jsons.update(layout_blocks)

    return jsons


def layout_generation(cfg: CFG, final_dir: Path = Path("."), position: int = 0) -> List[Dict[str, SMS_T]]:
    """
    Returns the information from the liveness analysis and also stores a dot file for each analyzed structure
    in "final_dir"
    """
    layout_dir = final_dir.joinpath(str(position))
    layout_dir.mkdir(parents=True, exist_ok=True)

    layouts_per_cfg = [layout_generation_cfg(cfg, layout_dir)]
    if cfg.subObjects is not None:
        layouts_per_cfg.extend(layout_generation(cfg.subObjects, final_dir, position + 1))

    return layouts_per_cfg
