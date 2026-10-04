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
import global_params.constants as constants
from parser.cfg import CFG
from parser.cfg_block_list import CFGBlockList
from parser.cfg_block import CFGBlock
from analysis.abstract_state import digraph_from_block_info
from graphs.algorithms import condense_to_dag, information_on_graph, compute_dominance_tree
from graphs.cfg import compute_loop_nesting_forest_graph
from liveness.liveness_analysis import LivenessAnalysisInfoSSA, construct_analysis_info, \
    perform_liveness_analysis_from_cfg_info
from liveness.utils import functions_inputs_from_components
from liveness.calling_convention import apply_calling_conventions, validate_calling_conventions
from liveness.stack_layout_methods import (compute_variable_depth, output_stack_layout, unify_stacks_brothers,
                                           compute_block_level, unification_block_dict, propagate_output_stack,
                                           forget_values, unify_stacks_dominant, block_events, tiers_order)

from timeit import default_timer as dtimer

global too_long_index
too_long_index = 0

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
                 cfg_graph: Optional[nx.DiGraph] = None, visualize:bool = False, junk: bool = True,
                 junk_strategy: str = "current", new_vars_order: str = "h1", edge_dominance: bool = True):
        self._component_id = object_id
        self._block_list = block_list
        self._liveness_info = liveness_info
        self._function_inputs = function_inputs
        # We store if it is the main component in order to preserve the stack elements
        self._is_main_component = is_main_component
        self._junk = junk
        # Experimental strategies for the junk and the order of the new variables (see output_stack_layout)
        self._junk_strategy = junk_strategy
        self._new_vars_order = new_vars_order

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

        # Blocks from which the function can return. The remaining ones end up in a terminal instruction
        # (e.g. a revert) and never return to the caller, so they can leave junk in the stack as the
        # main component does
        function_return_blocks = [block_id for block_id, block in block_list.blocks.items()
                                  if block.get_jump_type() == "FunctionReturn"]
        self._reaches_function_return = set(function_return_blocks)
        for block_id in function_return_blocks:
            self._reaches_function_return.update(nx.ancestors(self._cfg_graph, block_id))

        if constants.DEBUG:
            _loop_nesting_dir = name.joinpath("loop-nesting")
            _loop_nesting_dir.mkdir(exist_ok=True, parents=True)
            nx.nx_agraph.write_dot(self._loop_nesting_forest, _loop_nesting_dir.joinpath(f"{object_id}.dot"))

        # Guess: we need to traverse the code following the dominance tree in topological order
        # This is because in the dominance tree together with the SSA, all the nodes

        self._block_depth = compute_block_level(self._dominance_tree, self._start)
        self._unification_dict = unification_block_dict(block_list)

        # Joins reached through an edge block whose predecessor dominates the other predecessor (an if without
        # else once the critical edges are split). The stack of the conditional block is preserved along the
        # then-branch, as it was done before splitting (see _dominant_through_edge_block)
        self._dominant_edge_joins = self._compute_dominant_edge_joins() if edge_dominance else dict()
        self._joins_by_conditional: Dict[block_id_T, List[block_id_T]] = defaultdict(list)
        for join_id, (_, cond_id, _) in self._dominant_edge_joins.items():
            self._joins_by_conditional[cond_id].append(join_id)

    def _new_vars_order_function(self, block: CFGBlock):
        """
        Function that sorts the new variables placed in the output stack of the block (from top to bottom),
        or None for the default order (h1). The "tiers" order uses the events of the single successor
        """
        if self._new_vars_order != "tiers" or len(block.successors) != 1:
            return None
        successor_id = block.successors[0]
        successor_live_out = self._liveness_info[successor_id].out_state.vars_to_introduce
        successor_events = block_events(self._block_list.get_block(successor_id), successor_live_out)
        variable_depth_info = self._variable_order[block.block_id]
        return lambda variables: tiers_order(variables, variable_depth_info, successor_events, successor_live_out)

    def _can_have_junk(self, block_id):
        """
        Junk can be left in the stack in blocks that never return to a caller (all the blocks in the main
        component and the blocks in functions that cannot reach a function return), except inside loops,
        where it would accumulate across iterations
        """
        return self._junk and block_id not in self._loop_nesting_forest and \
            (self._is_main_component or block_id not in self._reaches_function_return)

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

                # The joins reached through an edge block are unified when their conditional block is processed
                assert next_block_id not in self._dominant_edge_joins, \
                    f"The join {next_block_id} must have been unified when processing its conditional block"

                # We avoid going through loop headers because it can confuse the algorithm
                if len(elements_to_unify) == 2 and ((
                        path := self._preserve_junk_dominance(elements_to_unify[0], elements_to_unify[1])) is not None):
                        # and all(self._loop_nesting_forest.successors(element) == 0
                        #         for element in path[1:] if element in self._loop_nesting_forest):
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
                output_stack = propagate_output_stack(input_stack, block.final_stack_elements, liveness_info.in_state.vars_to_introduce,
                                                      liveness_info.out_state.vars_to_introduce, self._variable_order[block_id],
                                                      block.split_instruction.in_args if block.split_instruction else [])

                junk_idx = len(output_stack)

            else:
                live_out = liveness_info.out_state.vars_to_introduce
                events = block_events(block, live_out) if self._junk_strategy == "simulated" else None
                output_stack, junk_idx = output_stack_layout(input_stack, block.final_stack_elements,
                                                             live_out,
                                                             self._variable_order[block_id],
                                                             self._can_have_junk(block_id),
                                                             self._junk_strategy, events,
                                                             self._new_vars_order_function(block)
                                                             )

            # We store the output stack in the dict, as we have built a new element
            # We forget about the junk, because we propagate it assuming there is no garbage
            output_stacks[block_id] = output_stack[:junk_idx]

        # If this block is the conditional block of a join reached through an edge block, the join is unified now,
        # before the then-branch is processed, so that the values preserved along it are known in time
        for join_id in self._joins_by_conditional.get(block_id, []):
            self._unify_through_edge_block(join_id, input_stacks, output_stacks)

        # We build the corresponding specification and store it in the block
        block_json = block.build_spec(substitute_duplicates(input_stack), output_stack)
        block_json["admits_junk"] = self._can_have_junk(block_id)
        block.spec = block_json

        return block_json

    def _compute_dominant_edge_joins(self) -> Dict[block_id_T, Tuple[block_id_T, block_id_T, List[block_id_T]]]:
        """
        Joins with two predecessors such that one of them is an edge block e (transparent for the stack) whose
        predecessor cond dominates the other predecessor, while the two predecessors do not dominate each other.
        Returns join -> (e, cond, path from cond to the other predecessor in the dominator tree). The liveness of
        e is extended with the values live at the exit of cond, so that e forwards the stack of cond as is
        """
        dominant_edge_joins = dict()
        for block_id, block in self._block_list.blocks.items():
            if constants.DEBUG and block.is_edge_block:
                # No edge block between a latch and its header: the successor does not dominate the edge block
                assert not nx.has_path(self._dominance_tree, block.get_jump_to(), block_id), \
                    f"Edge block {block_id} splits a back edge"

            # Same order as the unification (see unification_block_dict): as before splitting, only the first
            # predecessor can play the role of the dominating block
            predecessors = block.entries if block.entries else block.get_comes_from()
            if len(predecessors) != 2:
                continue
            edge_id, other_id = predecessors
            edge_block = self._block_list.get_block(edge_id)
            # Only the edge blocks that split a critical edge of the input CFG (an if without else). The ones
            # inserted by the merge pass lead to merged blocks, for which preserving the stack does not pay off
            if not edge_block.splits_critical_edge or self._preserve_junk_dominance(edge_id, other_id) is not None:
                continue
            cond_id = edge_block.get_comes_from()[0]
            path = self._preserve_junk_dominance(cond_id, other_id)
            if path is not None:
                dominant_edge_joins[block_id] = (edge_id, cond_id, path)
                cond_live_out = self._liveness_info[cond_id].out_state.vars_to_introduce
                self._liveness_info[edge_id].in_state.extra_values.update(cond_live_out)
                self._liveness_info[edge_id].out_state.extra_values.update(cond_live_out)
        return dominant_edge_joins

    def _unify_through_edge_block(self, join_id: block_id_T, input_stacks: Dict[str, List[str]],
                                  output_stacks: Dict[str, List[str]]) -> None:
        """
        Unifies the predecessors of a join reached through an edge block e, whose conditional block cond (just
        processed) dominates the other predecessor. As before splitting the critical edge, the stack of cond is
        preserved along the then-branch: e plays the role of cond in unify_stacks_dominant (its input stack is
        the output stack of cond and its liveness includes the values live at the exit of cond)
        """
        edge_id, cond_id, path = self._dominant_edge_joins[join_id]
        _, elements_to_unify, phi_instructions = self._unification_dict[edge_id]
        combined_liveness_info = {element: self._liveness_info[element].out_state.vars_to_introduce
                                  for element in elements_to_unify}
        combined_liveness_info[join_id] = self._liveness_info[join_id].in_state.vars_to_introduce

        (combined_output_stack,
         output_stacks_unified,
         values_to_propagate) = unify_stacks_dominant(join_id, elements_to_unify, combined_liveness_info,
                                                      phi_instructions, self._variable_order[join_id],
                                                      edge_id, self._edge_block_input(edge_id, output_stacks),
                                                      self._can_have_junk(edge_id))
        self.preserve_stack_dominant_path(path, output_stacks_unified[path[-1]], values_to_propagate)
        output_stacks.update(output_stacks_unified)
        input_stacks[join_id] = combined_output_stack

    def _edge_block_input(self, edge_id: block_id_T, output_stacks: Dict[str, List[str]]) -> List[var_id_T]:
        """
        Input stack of an edge block that has not been processed yet: the output stack of its predecessor
        (processed before, as it dominates the edge block), forgetting the deepest dead values if junk is allowed
        """
        input_stack = output_stacks[self._block_list.get_block(edge_id).get_comes_from()[0]]
        if self._can_have_junk(edge_id):
            input_stack = forget_values(input_stack, self._liveness_info[edge_id].in_state.vars_to_introduce)
        return input_stack

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
                try:
                    with open(self._sfs_dir.joinpath(block_name + ".json"), 'w') as f:
                        json.dump(specification, f, indent=4)
                except:
                    global too_long_index
                    # For block names that are too long (yeah... it happens)
                    with open(self._sfs_dir.joinpath(f"too_long_{too_long_index}.json"), 'w') as f:
                        json.dump(specification, f, indent=4)


def layout_generation_cfg(cfg: CFG, args: argparse.Namespace, final_dir: Path = Path("."),
                          components: Optional[Dict[str, set]] = None) -> Tuple[float, float]:
    """
    Generates the layout for all the blocks in the objects inside the CFG level, excluding sub-objects
    """
    x = dtimer()
    cfg_info = construct_analysis_info(cfg)
    results = perform_liveness_analysis_from_cfg_info(cfg_info)

    # The calling conventions permute the arguments of the functions, so the inputs are computed afterwards
    call_convention = getattr(args, "call_convention", "fixed")
    if call_convention != "fixed":
        for object_name, object_liveness in results.items():
            if call_convention == "best":
                # Only the functions in which the "orders" convention was cheaper (see main_execution)
                selected = getattr(args, "call_convention_selected", {}).get(object_name, set())
                conventions = apply_calling_conventions(cfg.objectCFG[object_name], object_liveness, "orders", selected)
                # The applied conventions are recorded to undo them (see main_execution.generate_with_best_conventions)
                if getattr(args, "record_conventions", None) is not None:
                    args.record_conventions[object_name] = conventions
            else:
                apply_calling_conventions(cfg.objectCFG[object_name], object_liveness, call_convention)
    component2inputs = functions_inputs_from_components(cfg)
    y = dtimer()

    component2block_list = cfg.generate_id2block_list()

    for object_name, object_liveness in results.items():
        for component_name, component_liveness in object_liveness.items():
            # Only some components (see main_execution.generate_with_best_conventions)
            if components is not None and component_name not in components.get(object_name, ()):
                continue
            layout = LayoutGeneration(component_name, component2block_list[object_name][component_name],
                                      component_liveness, component2inputs[object_name], final_dir,
                                      component_name == object_name,
                                      visualize=args.visualize, junk=args.junk,
                                      junk_strategy=getattr(args, "junk_strategy", "current"),
                                      new_vars_order=getattr(args, "new_vars_order", "h1"),
                                      edge_dominance=getattr(args, "edge_dominance", True))

            layout.build_layout(args.visualize)

    if constants.DEBUG:
        for object_name in results:
            validate_calling_conventions(cfg.objectCFG[object_name])

    return x, y


def layout_generation(cfg: CFG, args: argparse.Namespace,
                      final_dir: Path = Path("."), positions: List[str] = None) -> Tuple[float, float]:
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
