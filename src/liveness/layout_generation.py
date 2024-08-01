"""
Module that generates the layouts that are fed into the superoptimization algorithm.
In this case, we build different heuristics to choose the best layout transformation.
As there are heuristics that can be based on the results of preceeding blocks with the greedy algorithm,
in this module the greedy algorithm itself is invoked
"""
import heapq
from typing import Dict, List, Type, Any
import networkx as nx
from pathlib import Path


from parser.cfg_block_list import CFGBlockList
from parser.cfg_block import CFGBlock
from parser.cfg import CFG
from analysis.abstract_state import digraph_from_block_info
from graphs.algorithms import condense_to_dag, information_on_graph
from liveness.liveness_analysis import LivenessAnalysisInfo, construct_analysis_info, \
    perform_liveness_analysis_from_cfg_info


def unify_input_stacks(predecessor_stacks: List[List[str]], variable_depth_info: Dict[str, int]) -> List[str]:
    """
    Unifies the given stacks, according to the information already provided in variable depth info
    """
    pass


def unify_stacks(predecessor_stacks: List[List[str]], variable_depth_info: Dict[str, int]) -> List[str]:
    """
    Unifies the given stacks, according to the information already provided in variable depth info
    """
    needed_elements = set(elem for stack in predecessor_stacks for elem in stack)
    max_depth = max(variable_depth_info.values()) + 1 if len(variable_depth_info) > 0 else -1
    pairs = [(variable_depth_info.get(stack_elem, max_depth), stack_elem) for stack_elem in needed_elements]
    return [elem[1] for elem in sorted(pairs)]


def construct_code_from_block(block: CFGBlock, liveness_info: Dict[str, Any], variable_depth_info: Dict[str, int],
                              input_stacks: Dict[str, List[str]], output_stacks: Dict[str, List[str]]):
    """
    Constructs the specification for a given block, according to the input and output stacks
    """
    # First we retrieve the output stacks from the previous blocks
    predecessor_stacks = [output_stacks[predecessor] for predecessor in block.get_comes_from() if predecessor in output_stacks]
    input_stack = unify_stacks(predecessor_stacks, variable_depth_info)

    output_stack = unify_stacks([liveness_info[block.block_id].input_state.live_vars], variable_depth_info)
    # We build the corresponding specification
    block_json = {}

    # Modify the specification to update the input stack and output stack fields
    block_json["src_ws"] = input_stack
    block_json["tgt_ws"] = output_stack

    # TODO: temporal hack to output the input and output stacks
    block.input_stack = input_stack
    block.output_stack = output_stack

    input_stacks[block.block_id] = input_stack
    output_stacks[block.block_id] = output_stack

    return block_json


def construct_code_from_block_list(block_list: CFGBlockList, liveness_info: Dict[str, Any], depth_dict: Dict[str, int],
                                   variable_depth_dict: Dict[str, Dict[str, int]], start: str):
    """
    Naive implementation: just traverse the blocks and generate the src and tgt information according to the liveness
    information. In order to keep the stacks coherent, we traverse them according to the dominance tree
    """
    input_stacks = dict()
    output_stacks = dict()
    traversed = set()
    json_info = dict()

    pending_blocks = []
    heapq.heappush(pending_blocks, (0, 0, start))

    while pending_blocks:

        _, real_depth, block_name = heapq.heappop(pending_blocks)

        if block_name in traversed:
            continue

        traversed.add(block_name)

        # Retrieve the block
        current_block = block_list.get_block(block_name)

        block_specification = construct_code_from_block(current_block, liveness_info, variable_depth_dict[block_name],
                                                        input_stacks, output_stacks)

        json_info[block_name] = block_specification

        successors = [possible_successor for possible_successor in
                      [current_block.get_jump_to(), current_block.get_falls_to()] if possible_successor is not None]
        for successor in successors:
            if successor not in traversed:
                heapq.heappush(pending_blocks, (depth_dict[successor], real_depth + 1, successor))

    return json_info


def compute_variable_depth(liveness_info: Dict[str, LivenessAnalysisInfo], topological_order: List) -> Dict[str, Dict[str, int]]:
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
        for input_variable in liveness_info[node].input_state.live_vars:
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

        # Finally, we update the corresponding variables that are defined and used in the blocks
        for used_variable in block_info.uses:
            current_variable_depth_in[used_variable] = 0

        variable_depth_out[node] = current_variable_depth_out
        variable_depth_in[node] = current_variable_depth_in

    return variable_depth_out


def compute_block_level(dominance_tree: nx.DiGraph, start: str) -> Dict[str, int]:
    """
    Computes the block level according to the dominance tree
    """
    return nx.shortest_path_length(dominance_tree, start)


def unification_block_tuples(block_info: Dict[str, Any]):
    """
    Given the CFG, it finds those blocks that must unify their corresponding output stacks, due to jumping to the same
    block
    """
    unification_tuples = []
    for block_name, information in block_info.items():
        comes_from = information.block_info.comes_from
        if len(comes_from) > 1:
            unification_tuples.append([*comes_from])
    return unification_tuples


def var_order_repr(block_name: str, var_info: Dict[str, int]):
    """
    Str representation of a block name and the information on variables
    """
    text_format = [f"{block_name}:", *(f"{var_}: {idx}" for var_, idx in var_info.items())]
    return '\n'.join(text_format)


def print_stacks(block_name: str, block: CFGBlock):
    text_format = [f"{block_name}:", f"Src: {block.input_stack}", f"Tgt: {block.output_stack}"]
    return '\n'.join(text_format)


class LayoutGeneration:

    def __init__(self, object_id, block_list: CFGBlockList, liveness_info: Dict[str, LivenessAnalysisInfo], name: Path,
                 cfg_graph: nx.Graph = None):
        self._id = object_id
        self._block_list = block_list
        self._liveness_info = liveness_info

        if cfg_graph is None:
            self._cfg_graph = digraph_from_block_info(liveness_analysis_state.block_info
                                                      for liveness_analysis_state in liveness_info.values())
        else:
            self._cfg_graph = cfg_graph

        self._start = block_list.start_block

        immediate_dominators = nx.immediate_dominators(self._cfg_graph, self._start)
        self._dominance_tree = nx.DiGraph([v, u] for u, v in immediate_dominators.items() if u != self._start)

        nx.nx_agraph.write_dot(self._dominance_tree, name)
        self._block_order = list(nx.topological_sort(self._dominance_tree))

        self._variable_order = compute_variable_depth(liveness_info, self._block_order)

        renamed_graph = information_on_graph(self._cfg_graph, {name: var_order_repr(name, assignments)
                                                               for name, assignments in self._variable_order.items()})
        nx.nx_agraph.write_dot(renamed_graph, Path(name.parent).joinpath(name.name + "_vars.dot"))
        self._dir = name
        # Guess: we need to traverse the code following the dominance tree in topological order
        # This is because in the dominance tree together with the SSA, all the nodes

    def build_layout(self):
        """
        Builds the layout of the blocks from the given representation
        """
        json_info = construct_code_from_block_list(self._block_list, self._liveness_info,
                                                   compute_block_level(self._dominance_tree, self._start),
                                                   self._variable_order, self._start)

        renamed_graph = information_on_graph(self._cfg_graph, {block_name: print_stacks(block_name, block)
                                                               for block_name, block in self._block_list.blocks.items()})
        print(Path(self._dir.parent).joinpath(self._dir.name + "_stacks.dot"))
        nx.nx_agraph.write_dot(renamed_graph, Path(self._dir.parent).joinpath(self._dir.name + "_stacks.dot"))
        return json_info


def layout_generation(cfg: CFG, final_dir: Path = Path(".")) -> Dict[str, Dict[str, Any]]:
    """
    Returns the information from the liveness analysis and also stores a dot file for each analyzed structure
    in "final_dir"
    """
    cfg_info = construct_analysis_info(cfg)
    results = perform_liveness_analysis_from_cfg_info(cfg_info)
    jsons = dict()

    for component_name, liveness in results.items():
        cfg_info_suboject = cfg_info[component_name]["block_info"]
        digraph = digraph_from_block_info(cfg_info_suboject.values())

        if len(digraph) == 1:
            continue

        print("NODES", digraph.nodes)

        layout = LayoutGeneration(component_name, cfg.block_list[component_name], liveness,
                                  final_dir.joinpath(f"{component_name}_dominated.dot"), digraph)
        jsons[component_name] = layout.build_layout()

    return jsons
