"""
Module that generates the layouts that are fed into the superoptimization algorithm.
In this case, we build different heuristics to choose the best layout transformation.
As there are heuristics that can be based on the results of preceeding blocks with the greedy algorithm,
in this module the greedy algorithm itself is invoked
"""
import argparse
import collections
import heapq
import itertools
import json
from typing import Dict, List, Type, Any, Set, Tuple, Optional
import networkx as nx
from pathlib import Path
from itertools import zip_longest
from collections import defaultdict

from global_params.types import SMS_T, component_name_T, var_id_T, block_id_T
from parser.cfg import CFG
from parser.cfg_block_list import CFGBlockList
from parser.cfg_block import CFGBlock
from analysis.abstract_state import digraph_from_block_info
from graphs.algorithms import condense_to_dag, information_on_graph, compute_dominance_tree
from graphs.cfg import compute_loop_nesting_forest_graph
from liveness.liveness_analysis import LivenessAnalysisInfoSSA, construct_analysis_info, \
    perform_liveness_analysis_from_cfg_info
from liveness.utils import functions_inputs_from_components
from liveness.stack_layout_methods import (compute_variable_depth, output_stack_layout, unify_stacks_brothers,
                                           compute_block_level, unification_block_dict, propagate_output_stack,
                                           forget_values, unify_stacks_dominant)

from timeit import default_timer as dtimer

def substitute_duplicates(input_stack: List[var_id_T]):
    substituted = []
    added = set()
    for var_ in input_stack[::-1]:
        if var_ in added:
            substituted.append(f"a{len(added)}")
        else:
            substituted.append(var_)
            added.add(var_)

    return substituted[::-1]


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
    # text_format += [print_json_instr(instr) for instr in json_dict["user_instrs"]]
    return '\n'.join(text_format)


class LayoutGeneration:

    def __init__(self, object_id: str, block_list: CFGBlockList, liveness_info: Dict[str, LivenessAnalysisInfoSSA],
                 function_inputs: Dict[component_name_T, List[var_id_T]], name: Path, is_main_component: bool,
                 cfg_graph: Optional[nx.DiGraph] = None, visualize:bool = False, junk: bool = True):
        self._component_id = object_id
        self._block_list = block_list
        self._liveness_info = liveness_info
        self._function_inputs = function_inputs
        # We store if it is the main component in order to preserve the stack elements
        self._is_main_component = is_main_component
        self._junk = junk

        if cfg_graph is None:
            self._cfg_graph = digraph_from_block_info(liveness_analysis_state.block_info
                                                      for liveness_analysis_state in liveness_info.values())
        else:
            self._cfg_graph = cfg_graph

        self._start = block_list.start_block

        self._dominance_tree = compute_dominance_tree(self._cfg_graph, self._start)

        if visualize:
            _tree_dir = name.joinpath("tree")
            _tree_dir.mkdir(exist_ok=True, parents=True)

            nx.nx_agraph.write_dot(self._dominance_tree, _tree_dir.joinpath(f"{object_id}.dot"))

        self._block_order = list(nx.topological_sort(self._dominance_tree))

        self._variable_order = compute_variable_depth(liveness_info, self._block_order)

        renamed_graph = information_on_graph(self._cfg_graph, {name: var_order_repr(name, assignments)
                                                               for name, assignments in self._variable_order.items()})

        if visualize:
            _var_dir = name.joinpath("var_order")
            _var_dir.mkdir(exist_ok=True, parents=True)
            nx.nx_agraph.write_dot(renamed_graph, _var_dir.joinpath(f"{object_id}.dot"))

            self._layout_dir = name.joinpath("layouts")
            self._layout_dir.mkdir(exist_ok=True, parents=True)

            self._sfs_dir = name.joinpath("sfs")
            self._sfs_dir.mkdir(exist_ok=True, parents=True)

        self._loop_nesting_forest = compute_loop_nesting_forest_graph(self._cfg_graph)

        _loop_nesting_dir = name.joinpath("loop-nesting")
        _loop_nesting_dir.mkdir(exist_ok=True, parents=True)
        nx.nx_agraph.write_dot(self._loop_nesting_forest, _loop_nesting_dir.joinpath(f"{object_id}.dot"))

        # Guess: we need to traverse the code following the dominance tree in topological order
        # This is because in the dominance tree together with the SSA, all the nodes

        self._block_depth = compute_block_level(self._dominance_tree, self._start)
        self._unification_dict = unification_block_dict(block_list)

    def _can_have_junk(self, block_id):
        return self._is_main_component and block_id not in self._loop_nesting_forest and self._junk

    def _construct_code_from_block(self, block: CFGBlock, input_stacks: Dict[str, List[str]],
                                   output_stacks: Dict[str, List[str]]):
        """
        Constructs the specification for a given block, according to the input and output stacks
        """
        block_id = block.block_id
        liveness_info = self._liveness_info[block_id]

        block.set_liveness({"in": liveness_info.in_state.live_vars,
                            "out": liveness_info.out_state.live_vars})

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

        # We forget the deepest elements in the main component
        if self._can_have_junk(block_id):
            input_stack = forget_values(input_stack, self._liveness_info[block_id].in_state.vars_to_introduce)

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
                combined_liveness_info = {element_to_unify: self._liveness_info[element_to_unify].out_state.vars_to_introduce
                                          for element_to_unify in elements_to_unify}
                combined_liveness_info[next_block_id] = self._liveness_info[next_block_id].in_state.vars_to_introduce

                # We avoid going through loop headers because it can confuse the algorithm
                if len(elements_to_unify) == 2 and ((
                        path := self._preserve_junk_dominance(elements_to_unify[0], elements_to_unify[1])) is not None)\
                        and all(self._loop_nesting_forest.successors(element) == 0
                                for element in path[1:] if element in self._loop_nesting_forest):
                    (combined_output_stack,
                     output_stacks_unified,
                     values_to_propagate) = unify_stacks_dominant(next_block_id,
                                                                  elements_to_unify,
                                                                  combined_liveness_info,
                                                                  phi_instructions,
                                                                  self._variable_order[
                                                                      next_block_id],
                                                                  block_id, input_stack.copy(),
                                                                  self._can_have_junk(block_id))
                    # We take the last output stack
                    self.preserve_stack_dominant_path(path, output_stacks_unified[path[-1]], values_to_propagate)

                else:
                    # If it is the main component, we do not care about the state of the stack afterwards
                    combined_output_stack, output_stacks_unified = unify_stacks_brothers(next_block_id,
                                                                                         elements_to_unify,
                                                                                         combined_liveness_info,
                                                                                         phi_instructions,
                                                                                         self._variable_order[
                                                                                             next_block_id],
                                                                                         block_id, input_stack.copy(),
                                                                                         self._can_have_junk(block_id))

                # Update the output stacks with the ones generated from the unification
                output_stacks.update(output_stacks_unified)
                output_stack = output_stacks[block_id]

                # The combined output stack is the input stack of the successor
                input_stacks[next_block_id] = combined_output_stack

        if output_stack is None:
            if block.get_jump_type() in ["terminal", "mainExit"] or block.previous_type in ["terminal", "mainExit"]:
                # We just need to place the corresponding elements in the top of the stack
                output_stack = propagate_output_stack(input_stack, block.final_stack_elements,
                                                      liveness_info.out_state.vars_to_introduce, self._variable_order[block_id],
                                                      block.split_instruction.in_args if block.split_instruction else [])

                junk_idx = len(output_stack)

            else:
                output_stack, junk_idx = output_stack_layout(input_stack, block.final_stack_elements,
                                                             liveness_info.out_state.vars_to_introduce,
                                                             self._variable_order[block_id],
                                                             self._can_have_junk(block_id)
                                                             )

            # We store the output stack in the dict, as we have built a new element
            # We forget about the junk, because we propagate it assuming there is no garbage
            output_stacks[block_id] = output_stack[:junk_idx]

        # We build the corresponding specification and store it in the block
        block_json = block.build_spec(substitute_duplicates(input_stack), output_stack)
        block_json["admits_junk"] = self._can_have_junk(block_id)
        block.spec = block_json

        return block_json

    def _preserve_junk_dominance(self, block1: block_id_T, block2: block_id_T) -> Optional[List[block_id_T]]:
        """
        Returns the path that connects u and v iff u dom v and we want to preserve the path that connects u to v.
        Otherwise, returns None.
        """
        if nx.has_path(self._dominance_tree, block1, block2):
            shortest_path = nx.shortest_path(self._dominance_tree, block1, block2)
        else:
            return None

        # The path must have at least 6 nodes (3 intermediate + block1 and block2)
        if len(shortest_path) < 6:
            return shortest_path

        # Otherwise, we check how many of those blocks admit junk. If > 3 do not admit junk,
        # then we prefer to combine the phis.
        num_without_junk = 0

        # TODO: count successors with junks that are not in the path
        for block_id in shortest_path[1:-1]:
            for succ in self._cfg_graph.successors(block_id):
                num_without_junk += int(not self._can_have_junk(succ))

        if num_without_junk > 3:
            return None
        else:
            return shortest_path

    def preserve_junk_header(self, block_id: block_id_T, input_stack: List[var_id_T]):
        """
        Given the input stack of the header of a block, preserves the information as is
        by marking that the junk elements must not be erased
        """
        # Mark the garbage as live to preserve it as is
        if block_id in self._loop_nesting_forest and len(
                list(self._loop_nesting_forest.successors(block_id))) > 0:
            next_block_liveness = self._liveness_info[block_id].in_state.vars_to_introduce
            junk = [value for value in input_stack
                    if value not in next_block_liveness]

            if len(junk) > 0:

                # We also mark the out state of the current block
                self._liveness_info.out_state.extra_values.update(junk)

                for succ in self._loop_nesting_forest.successors(block_id):
                    self._liveness_info[succ].in_state.extra_values.update(junk)
                    self._liveness_info[succ].out_state.extra_values.update(junk)

    def preserve_stack_dominant_path(self, path: List[block_id_T],
                                     out_stack_last: List[var_id_T],
                                     values_to_propagate: Set[var_id_T]):
        """
        Preserves the values of the stack when two stacks are unified s.t
        the original one dominates the other one. A path is passed
        that connects those two values
        """
        # We want to propagate the liveness backwards
        next_block_liveness = self._liveness_info[path[-1]].out_state.vars_to_introduce

        # Consider only the deepest elements, without the split instruction
        # We choose the junk for the last block instead of the first one due to the trick of
        # "forgetting" values that are very deep within the stack
        junk = set(value for value in out_stack_last
                   if value not in next_block_liveness)

        # Combined values: values_to_propagate from phi functions + junk
        combined_propagation = values_to_propagate.union(junk)

        # TRICK: We have to preserve the values in between that are lost otherwise
        if len(combined_propagation) > 0:

            # We start with the last element upwards
            elements_to_traverse = [path[-1]]
            already_traversed = set()
            while elements_to_traverse:
                next_block = elements_to_traverse.pop()

                # We stop when reaching the first element
                if next_block in already_traversed or next_block == path[0]:
                    continue
                already_traversed.add(next_block)
                self._liveness_info[next_block].in_state.extra_values.update(combined_propagation)
                self._liveness_info[next_block].out_state.extra_values.update(combined_propagation)

                # Extend backwards
                elements_to_traverse.extend(self._cfg_graph.predecessors(next_block))

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

    def build_layout(self, visualize: bool = False) -> None:
        """
        Builds the layout of the blocks from the given representation and stores it inside the CFG
        """
        json_info = self._construct_code_from_block_list()

        # Here we just store the layouts and the sfs
        renamed_graph = information_on_graph(self._cfg_graph,
                                             {block_name: print_stacks(block_name, json_info[block_name])
                                              for block_name in
                                              self._block_list.blocks})

        if visualize:
            nx.nx_agraph.write_dot(renamed_graph, self._layout_dir.joinpath(f"{self._component_id}.dot"))
            for block_name, specification in json_info.items():
                with open(self._sfs_dir.joinpath(block_name + ".json"), 'w') as f:
                    json.dump(specification, f)



def layout_generation_cfg(cfg: CFG, args: argparse.Namespace, final_dir: Path = Path(".")) -> None:
    """
    Generates the layout for all the blocks in the objects inside the CFG level, excluding sub-objects
    """
    x = dtimer()
    cfg_info = construct_analysis_info(cfg)
    component2inputs = functions_inputs_from_components(cfg)
    results = perform_liveness_analysis_from_cfg_info(cfg_info)
    y = dtimer()

    component2block_list = cfg.generate_id2block_list()
    
    for object_name, object_liveness in results.items():
        for component_name, component_liveness in object_liveness.items():
            layout = LayoutGeneration(component_name, component2block_list[object_name][component_name],
                                      component_liveness, component2inputs, final_dir, component_name == object_name,
                                      visualize=args.visualize, junk=args.junk)

            layout.build_layout(args.visualize)

    return x, y


def layout_generation(cfg: CFG, args: argparse.Namespace,
                      final_dir: Path = Path("."), positions: List[str] = None) -> None:
    """
    Returns the information from the liveness analysis and also stores a dot file for each analyzed structure
    in "final_dir"
    """
    if positions is None:
        positions = ["0"]
        

    layout_dir = final_dir.joinpath('_'.join([str(position) for position in positions]))
    layout_dir.mkdir(parents=True, exist_ok=True)
        
    init_time, end_time = layout_generation_cfg(cfg, args, layout_dir)

    total_x = init_time
    total_y = end_time
    for i, (cfg_name, cfg_object) in enumerate(cfg.get_objects().items()):

        sub_object = cfg_object.get_subobject()
        if sub_object is not None:
            x, y = layout_generation(sub_object, args, final_dir, positions + [str(i)])
            total_x+=x
            total_y+=y

    return total_x, total_y
