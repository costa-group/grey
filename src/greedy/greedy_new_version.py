#!/usr/bin/env python3
import json
import logging
import resource
import sys
from typing import List, Dict, Tuple, Set, Optional, Generator, Union
from collections import defaultdict, Counter
import traceback
import networkx as nx
from networkx.algorithms.traversal.depth_first_search import dfs_tree
from greedy.greedy_info import GreedyInfo
from analysis.greedy_validation import check_execution_from_ids


# from analysis.greedy_validation import check_execution_from_ids
from global_params.types import var_id_T, instr_id_T, instr_JSON_T, SMS_T
from greedy.utils import compute_max_n_elements

# Specific type to identify which positions corresponds to the ones
# in the current and final stacks
cstack_pos_T = int
fstack_pos_T = int

# Annotation for the maximum stack depth that can be managed through operations
STACK_DEPTH = 16


def idx_wrt_cstack(idx: fstack_pos_T, cstack: List, fstack: List) -> cstack_pos_T:
    """
    Given a position w.r.t fstack, returns the corresponding position w.r.t cstack
    """
    return idx - len(fstack) + len(cstack)


def idx_wrt_fstack(idx: cstack_pos_T, cstack: List, fstack: List) -> fstack_pos_T:
    """
    Given a position w.r.t cstack, returns the corresponding position w.r.t fstack
    """
    return idx - len(cstack) + len(fstack)


def top_relative_position_to_fstack(cstack: List[var_id_T], fstack: List[var_id_T]) -> int:
    return idx_wrt_fstack(0, cstack, fstack)


def extract_idx_from_id(instr_id: str) -> int:
    return int(instr_id.split('_')[-1])


def cheap(instr: instr_JSON_T) -> bool:
    """
    Cheap computations are those who take one instruction (i.e. inpt_sk is empty)
    """
    return len(instr['inpt_sk']) == 0 and instr["size"] <= 2


def decrement_and_clean(counter: Counter, key):
    counter[key] -= 1  # Decrement the count
    if counter[key] == 0:  # Remove the key if the count reaches zero
        del counter[key]


class SymbolicState:
    """
    A symbolic state includes a stack, a dict indicating the number of total uses of each instruction,
    the instructions that can be computed and the variables that must be duplicated
    """

    def __init__(self, initial_stack: List[var_id_T], dependency_graph: nx.DiGraph, relevant_nodes: Set[instr_id_T],
                 stack_var_copies_needed: Dict[var_id_T, int], user_instrs: List[instr_JSON_T],
                 final_stack: List[var_id_T]) -> None:
        self.debug_mode = True

        self.stack: List[var_id_T] = initial_stack.copy()
        self.final_stack: List[var_id_T] = final_stack # Not necessary to dup

        # The dependency graph with the instructions that can be computed due to
        # its arguments are already computed
        self.dep_graph: nx.DiGraph = dependency_graph.copy()

        # Relevant nodes that must be considered as possible computations
        self.relevant_nodes: Set[instr_id_T] = relevant_nodes.copy()

        # Terms that are cheap to compute
        self.cheap_terms_to_compute: Set[var_id_T] = {output_var for instr in user_instrs if cheap(instr)
                                                      for output_var in instr["outpt_sk"]}

        # Variables that need to be duplicated and already in the stack
        self.variables_to_dup: Set[var_id_T] = {stack_var for stack_var in initial_stack
                                                if stack_var_copies_needed[stack_var] > 0}

        self.stack_var_copies_needed: Dict[var_id_T, int] = stack_var_copies_needed.copy()

        # Check method for more information
        self._determine_solved(initial_stack, final_stack)

        # Number of times each variable is computed in the stack
        self.n_computed: Counter = Counter(initial_stack)
        
        # Stack variables that have been moved to the memory due to accessing deeper elements
        self.vars_in_memory: Set[var_id_T] = set()

        # Elements that need to be fixed afterwards. Does not necessarily match
        # with vars_in_memory because SET/GET combinations do not need to be fixed
        self.elements_to_fix: Set[var_id_T] = set()

        # Links every variable to an instruction in which they were accessible and how deep within the stack
        # can be reached
        self.reachable: Dict[var_id_T, Tuple[int, int]] = {element: (0, i)
                                                           for i, element in enumerate(initial_stack[:STACK_DEPTH])}

        # Number of instructions that have been applied so far. Needed for computing reachable
        self.modifications: int = 0

        # Counter for the number of times an element must be retrieved
        # from the memory
        self.get_count: Counter = Counter()

        # Computed elements
        self.computed: Set[var_id_T] = set()

        # Recursive information that is stored when
        # invoking the recursive greedy
        self._recursive_information = []

        # Candidates we skip due to recursion
        self.forbidden_candidates = set()

        # Debug mode: store all the ops applied and the stacks before and after
        if self.debug_mode:
            self.trace: List[Tuple[List[var_id_T], instr_id_T]] = [(self.stack.copy(), "Initial")]

    def _determine_solved(self, initial_stack: List[var_id_T], final_stack: List[var_id_T]):
        # Solved: positions in the final stack that contain elements in the correct position
        solved: Set[fstack_pos_T] = {len(final_stack) - i - 1
                                     for i, (ini_var, fin_var) in enumerate(zip(reversed(initial_stack),
                                                                                reversed(final_stack)))
                                          if ini_var == fin_var}

        # We store instead the elements not solved, as these are the ones we need to study
        self.not_solved = set(range(len(self.final_stack))).difference(solved)

        # Maximum element that is sorted (i.e. elements from that point on must not be modified
        # in the current stack)
        self.max_solved = 0 if len(self.not_solved) == 0 else max(self.not_solved) + 1

    def _remove_solved(self, idx: fstack_pos_T):
        """
        Annotates that the idx is no longer solved
        """
        try:
            if idx >= 0:
                self.not_solved.add(idx)
        except KeyError:
            pass

    def _add_solved(self, idx: fstack_pos_T):
        """
        Annotates that the idx is solved, updating the maximum value if necessary
        """
        try:
            self.not_solved.remove(idx)

            # TODO: use here an ordered set that preserves order when inserting and removing elements
            if idx + 1 == self.max_solved:
                if len(self.not_solved) == 0:
                    self.max_solved = 0
                else:
                    self.max_solved = max(self.not_solved) + 1

        except KeyError:
            pass

    def _check_idx_solved_cstack(self, idx: cstack_pos_T):
        """
        Checks if the index in current stack is now solved or not
        """
        fstack_pos = self.idx_wrt_fstack(idx)
        self._remove_solved(fstack_pos)
        var_elem = self.stack[idx]
        if 0 <= fstack_pos < len(self.final_stack) and self.final_stack[fstack_pos] == var_elem:
            self._add_solved(fstack_pos)

    def _reachable_last_position(self):
        """
        Aims to add the deepest element of the stack to the reachable
        """
        new_available_position = min(STACK_DEPTH - 1, len(self.stack) - 1)
        if new_available_position >= 0:
            self.reachable[self.stack[new_available_position]] = self.modifications, new_available_position

    def idx_wrt_fstack(self, idx: cstack_pos_T) -> fstack_pos_T:
        """
        Conversion of the idx in the current stack to its corresponding position in the final stack
        """
        return idx_wrt_fstack(idx, self.stack, self.final_stack)

    def idx_wrt_cstack(self, idx: fstack_pos_T) -> cstack_pos_T:
        """
        Conversion of the idx in the final stack to its corresponding position in the current stack
        """

        return idx_wrt_cstack(idx, self.stack, self.final_stack)

    def swap(self, x: int) -> List[instr_id_T]:
        """
        Stores the top of the stack in the local with index x. in_position marks whether the element is
        solved in flocals
        """
        assert 0 < x < len(self.stack), f"Swapping with index {x} a stack of {len(self.stack)} elements: {self.stack}"
        self.stack[0], self.stack[x] = self.stack[x], self.stack[0]

        # Var copies: no modification, as we are just moving two elements

        # Solved: Check if either positions 0 or x are solved
        self._check_idx_solved_cstack(0)
        self._check_idx_solved_cstack(x)

        # N computed: no modification, as we are just moving two elements

        if self.debug_mode:
            self.trace.append((self.stack.copy(), f"SWAP{x}"))

        self.modifications += 1

        return [f"SWAP{x}"]

    def dup(self, x: int) -> List[instr_id_T]:
        """
        Tee instruction in local with index x. in_position marks whether the element is solved in flocals
        """
        idx = x - 1
        assert 0 <= idx < len(self.stack), \
            f"Duplicating index {x} in a stack in {len(self.stack)} elements: {self.stack}"
        new_topmost = self.stack[idx]
        self.stack.insert(0, new_topmost)

        # Var copies: we increment the element that we have duplicated
        self.stack_var_copies_needed[new_topmost] -= 1

        # Variables to dup: remove the element from this list if we have computed all the copies
        if self.stack_var_copies_needed[new_topmost] == 0:
            self.variables_to_dup.remove(new_topmost)

        # Solved: only the duplicated element can modify the solved elements, being added if
        # in the new topmost element is correctly placed
        fstack_idx = self.idx_wrt_fstack(0)

        if fstack_idx >= 0 and self.final_stack[fstack_idx] == new_topmost:
            self._add_solved(fstack_idx)

        # N computed: add one to the element we have computed
        self.n_computed[new_topmost] += 1

        if self.debug_mode:
            self.trace.append((self.stack.copy(), f"DUP{x}"))

        self.modifications += 1

        return [f"DUP{x}"]

    def pop(self) -> List[instr_id_T]:
        """
        Drops the last element
        """
        stack_var = self.stack.pop(0)

        # Var copies: we add one because the stack var is totally removed from the encoding
        self.stack_var_copies_needed[stack_var] += 1

        # Solved: just check whether the old topmost position was in solved
        self._remove_solved(self.idx_wrt_fstack(-1))

        # N computed: substract one to the element we have removed
        decrement_and_clean(self.n_computed, stack_var)

        # Reachable: only the last one if it was not already accessible
        self._reachable_last_position()

        if self.debug_mode:
            self.trace.append((self.stack.copy(), "POP"))

        self.modifications += 1

        return ["POP"]

    def consume_element(self) -> var_id_T:
        """
        Consumes element in order to compute an instruction
        """
        stack_var = self.stack.pop(0)

        # Var copies: it is not affected, as we are just consuming the elements for an operation

        # Solved: just check whether the old topmost position was in solved
        self._remove_solved(self.idx_wrt_fstack(-1))

        # N computed: substract one to the element we have consumed
        decrement_and_clean(self.n_computed, stack_var)

        # Reachable: only the last one if it was not accessible
        self._reachable_last_position()

        return stack_var

    def insert_element(self, instr: instr_JSON_T, output_var: var_id_T) -> None:
        """
        Insert an element as a result of computing an instruction
        """
        self.stack.insert(0, output_var)

        # Var copies: remove one, as we have introduced a stack variable
        self.stack_var_copies_needed[output_var] -= 1

        # If we need to duplicate it (because it is not cheap), we annotate that
        if not cheap(instr) and self.stack_var_copies_needed[output_var] > 0:
            self.variables_to_dup.add(output_var)

        # Solved: only the introduced element can modify the solved elements, being added if
        # in the new topmost element is correctly placed
        fstack_idx = self.idx_wrt_fstack(0)

        if fstack_idx >= 0 and self.final_stack[fstack_idx] == output_var:
            self._add_solved(fstack_idx)

        # N computed: add one to the element we have inserted
        self.n_computed[output_var] += 1

    def uf(self, instr: instr_JSON_T) -> List[instr_id_T]:
        """
        Symbolic execution of instruction instr. Additionally, checks the arguments match if debug mode flag is enabled
        """
        consumed_elements = [self.consume_element() for _ in range(len(instr['inpt_sk']))]

        # Neither liveness nor var uses are affected by consuming elements, as these elements are just being embedded
        # into a new term
        # Debug mode to check the pop args from the stack match
        if self.debug_mode:
            if instr['commutative']:
                # Compare them as multisets
                assert Counter(consumed_elements) == Counter(instr['inpt_sk']), \
                    f"{instr['id']} is not consuming the correct elements from the stack" \
                    f"Consumed elements: {consumed_elements}\nRequired elements: {instr['inpt_sk']}"
            else:
                # Compare them as lists
                assert consumed_elements == instr['inpt_sk'], \
                    f"{instr['id']} is not consuming the correct elements from the stack.\n" \
                    f"Consumed elements: {consumed_elements}\nRequired elements: {instr['inpt_sk']}"

        self.modifications += 1

        # We introduce the new elements
        for i, output_var in enumerate(instr['outpt_sk']):
            self.insert_element(instr, output_var)

            # We always insert in the first position,
            # so we need to consider the index in reversed order
            self.reachable[output_var] = self.modifications, len(instr["outpt_sk"]) - i - 1

        if instr["id"] in self.dep_graph.nodes:
            self.dep_graph.remove_node(instr["id"])

        if instr["id"] in self.relevant_nodes:
            self.relevant_nodes.remove(instr["id"])

        # Add to computed
        self.computed.add(instr["id"])

        if self.debug_mode:
            self.trace.append((self.stack.copy(), instr["id"]))

        return [instr["id"]]

    def from_memory(self, var_elem: var_id_T, to_fix: bool) -> List[instr_id_T]:
        """
        Assumes the value is retrieved from memory
        """
        self.stack.insert(0, var_elem)

        # Var uses: we increment the element that we have retrieved from memory
        self.stack_var_copies_needed[var_elem] -= 1

        # Solved: same as duplication
        fstack_idx = self.idx_wrt_fstack(0)

        if fstack_idx >= 0 and self.final_stack[fstack_idx] == var_elem:
            self._add_solved(fstack_idx)

        if self.debug_mode:
            self.trace.append((self.stack.copy(), f"VGET({var_elem})"))

        # N computed: add one to the element we have added
        self.n_computed[var_elem] += 1

        # An element must be fixed because it is retrieved
        # as part of a computation (not solving a permutation)
        if to_fix:
            self.elements_to_fix.add(var_elem)

        # Add one to the number of times an element is retrieved
        self.get_count.update(var_elem)

        self.modifications += 1

        return [f"VGET({var_elem})"]

    def store_in_memory(self):
        """
        Stores the topmost value in memory. Its behaviour is similar to POP
        """
        stack_var = self.stack.pop(0)
        self.vars_in_memory.add(stack_var)

        # Var copies: we add one because the stack var is totally removed from the encoding
        self.stack_var_copies_needed[stack_var] += 1

        # Solved: just check whether the old topmost position was in solved
        self._remove_solved(self.idx_wrt_fstack(-1))

        # N computed: substract one to the element we have removed
        decrement_and_clean(self.n_computed, stack_var)

        if self.debug_mode:
            self.trace.append((self.stack.copy(), f"VSET({stack_var})"))

        self.modifications += 1

        # Reachable: only the last one if it was not accessible
        self._reachable_last_position()

        return [f"VSET({stack_var})"]

    def top_stack(self) -> Optional[var_id_T]:
        return None if len(self.stack) == 0 else self.stack[0]

    def negative_idx2positive(self, idx: int) -> int:
        """
        Converts a negative index (-1 from the last element and so on) to the corresponding positive one
        """
        positive_idx = idx + len(self.stack)
        assert -1 <= positive_idx < len(self.stack), f"Attempting to convert an invalid negative index {idx}, " \
                                                     f"in a stack with {len(self.stack)} elements"
        return positive_idx

    def positive_idx2negative(self, idx: int) -> int:
        """
        Converts a positive index to the corresponding positive one (-1 to the last one and so on).
        It allows the index -1
        """
        negative_idx = idx - len(self.stack)
        assert 0 > negative_idx >= -len(self.stack) - 1, f"Attempting to convert an invalid positive index {idx}, " \
                                                         f"in a stack with {len(self.stack)} elements"
        return negative_idx

    def is_in_range(self, negative_idx: cstack_pos_T) -> bool:
        """
        Determines whether the idx is within the range of the stack
        """
        return 0 <= negative_idx < len(self.stack)

    def is_in_negative_range(self, negative_idx: cstack_pos_T) -> bool:
        """
        Determines whether the idx is within the range of the stack, considering it is negative
        """
        return 0 > negative_idx >= - len(self.stack)

    def first_swap(self, var_elem: var_id_T) -> int:
        """
        First position in which an element can be accessed for a swap instruction.
        It must not be solved. If not possible to find such position, returns 100000
        """
        for position, element in enumerate(self.stack):
            if position > STACK_DEPTH:
                break
            elif element == var_elem and position in self.not_solved:
                return position
        return 100000

    def is_accessible_dup(self, var_elem: var_id_T) -> bool:
        """
        Checks whether the variable element can be accessed for a dup instruction
        """
        return var_elem in self.stack and self.stack.index(var_elem) < STACK_DEPTH

    def first_occurrence(self, var_elem: var_id_T) -> int:
        """
        Returns the first position in which the element appears
        """
        try:
            return self.stack.index(var_elem)
        except:
            return -1

    def last_occurrence(self, var_elem: var_id_T) -> int:
        """
        Returns the last position in which the element appears
        """
        for idx, stack_elem in enumerate(self.stack[::-1]):
            if stack_elem == var_elem:
                return len(self.stack) - 1 - idx
        return -1

    def last_swap_occurrence(self, var_elem: var_id_T, min_pos: cstack_pos_T = 0) -> int:
        """
        Returns the last accessible position in which the element appears and can be swapped, considering
        positions lower or equal than min_pos cannot be accessed
        """
        current_idx = min(STACK_DEPTH, len(self.stack) - 1)

        while current_idx > min_pos:
            stack_elem = self.stack[current_idx]

            # Find the last occurrence in which the element is not placed in its position
            if stack_elem == var_elem:
                final_idx = self.idx_wrt_fstack(current_idx)
                if final_idx < 0:
                    return current_idx
                elif 0 <= final_idx < len(self.final_stack) and self.final_stack[final_idx] != var_elem:
                    return current_idx
            current_idx -= 1

        return -1

    def has_computations(self):
        """
        Checks if the current state has still computations left to do
        """
        # TODO: remove elements once they have 0 copies left and just check length
        return any(value > 0 for value in self.stack_var_copies_needed.values()) or len(self.relevant_nodes) > 0

    def var_elem_can_be_reused(self, var_elem: var_id_T, min_pos: cstack_pos_T) -> bool:
        """
        Checks if there is an accessible element that can be swapped and returns its position. Returns -1 if it
        is not possible
        """
        # Two possible positions: the element is repeated more than one in the stack (from min_pos)
        # or no more copies are needed. In order to simplify the computation, we add a first check
        # with self.n_computed[var_elem]
        return (self.n_computed[var_elem] > 1 and self.stack[(min_pos + 1):].count(var_elem) >= 1) \
                or self.stack_var_copies_needed[var_elem] == 0

    def position_to_swap(self, var_elem: var_id_T, min_pos: cstack_pos_T) -> int:
        """
        Returns an available position to which the current element can be placed, ranging from min_pos onwards. Returns
        -1 if either there is no such position or there is no element to reuse
        """
        if self.var_elem_can_be_reused(var_elem, min_pos):
            return self.last_swap_occurrence(var_elem, min_pos)
        return -1

    def candidates(self) -> Tuple[List[instr_id_T], Set[var_id_T], Set[var_id_T]]:
        """
        Returns the possible candidates from the pool of available instructions, cheap instructions
        and stack variables that are needed to be duplicated
        """
        return [id_ for id_ in self.relevant_nodes if (id_ not in self.dep_graph or self.dep_graph.out_degree(id_) == 0) and id_ not in self.forbidden_candidates], \
            self.cheap_terms_to_compute, self.variables_to_dup

    def elements_to_dup(self) -> int:
        """
        Returns how many elements can be duplicated
        """
        return sum(self.stack_var_copies_needed[stack_var] for stack_var in self.variables_to_dup
                   if self.is_accessible_dup(stack_var))

    def __repr__(self):
        return str(self.stack)

    def update_final_reachable(self, num_instrs: int):
        """
        Updates the reachability dict with the information from the final dict
        """
        for i, element in enumerate(self.final_stack[:STACK_DEPTH]):
            self.reachable[element] = num_instrs, i

    def recursive_state(self, instr: instr_JSON_T,
                        new_final_stack: List[var_id_T],
                        relevant_nodes_to_add: Set[instr_id_T]):
        """
        Modifies the state for performing a recursive greedy
        in order to compute an operation with multiple inputs
        """
        # The change is that I want to produce the final stack with
        # the input elements on top. This affects the final stack and the solved
        self._recursive_information.append((self.final_stack, instr["id"]))
        self.final_stack = new_final_stack

        # We generate the solved information with the new sets
        self._determine_solved(self.stack, self.final_stack)
        self.forbidden_candidates.add(instr["id"])

        # As a result, new operations must
        # be considered as relevant nodes if they haven't been computed
        self.relevant_nodes.update({node for node in relevant_nodes_to_add if node not in self.computed})

    def restore_state(self):
        """
        Restores the state after performing the recursive greedy
        """
        self.final_stack, instr_id = self._recursive_information.pop()
        # We recompute the solved elements
        self._determine_solved(self.stack, self.final_stack)
        self.forbidden_candidates.remove(instr_id)


class SMSgreedy:

    def __init__(self, json_format: SMS_T):
        self.debug_mode: bool = True

        self.name = json_format["name"]
        # How many elements are placed in the correct position and cannot be moved further in a computation
        self.fixed_elements: int = 0
        self._user_instr: List[instr_JSON_T] = json_format['user_instrs']
        self._initial_stack: List[var_id_T] = json_format['src_ws']
        self._final_stack: List[var_id_T] = json_format['tgt_ws']
        self._deps: List[Tuple[var_id_T, var_id_T]] = json_format['dependencies']
        self.debug_logger = DebugLogger()

        # Note: we assume function invocations might have several variables in 'outpt_sk'
        self._var2instr = {var: ins for ins in self._user_instr for var in ins['outpt_sk']}
        self._id2instr = {ins['id']: ins for ins in self._user_instr}
        self._var2id = {var: ins['id'] for ins in self._user_instr for var in ins['outpt_sk']}
        self._var2pos_stack = self._compute_var2pos(self._final_stack)
        self._instrs_with_deps = {instr_id for dep in self._deps for instr_id in dep}

        self._stack_var_copies_needed = self._compute_var_total_uses()
        dep_graph = self._compute_dependency_graph()
        self._condensed_graph = self._condense_graph(dep_graph)

        # Nodes that are considered computations
        self._relevant_nodes = set(self._condensed_graph.nodes)

        self.debug_logger.debug_message(f"{self._relevant_nodes}")
        nx.nx_agraph.write_dot(dep_graph, "dependency.dot")
        nx.nx_agraph.write_dot(self._condensed_graph, "condensed.dot")

        # Computed for all nodes in case we recursively apply the greedy
        tree_dict = self._generate_dataflow_tree(dep_graph.nodes)
        self._instr2max_n_elems = self._max_n_elements_from_tree(tree_dict)

        # Determine which topmost elements can be reused in the graph
        self._top_can_be_used = {}

        for instr in self._user_instr:
            self._compute_top_can_used(instr, self._top_can_be_used)

        self.must_compute_all = False

    def _compute_var_total_uses(self) -> Dict[var_id_T, int]:
        """
        Computes how many times each var must be computed due to appearing either in the final stack or as a subterm
        for other terms. It can be negative for stack variables that must be popped
        """
        var_uses = defaultdict(lambda: 0)

        for var_stack in self._initial_stack:
            var_uses[var_stack] -= 1

        # Count vars in the final stack
        for var_stack in self._final_stack:
            var_uses[var_stack] += 1

        # Count vars as input of other instrs
        for instr_id, instr in self._id2instr.items():
            for subterm_var in instr['inpt_sk']:
                var_uses[subterm_var] += 1

        return var_uses

    def _compute_var2pos(self, var_list: List[var_id_T]) -> Dict[var_id_T, List[int]]:
        """
        Dict that links each stack variable that appears in a var list to the
        list of positions it occupies
        """
        var2pos = defaultdict(lambda: [])

        for i, stack_var in enumerate(var_list):
            var2pos[stack_var].append(i)

        return var2pos

    def _compute_dependency_graph(self) -> nx.DiGraph:
        """
        We generate two dependency graphs: one for direct relations (i.e. one term embedded into another)
        and other with the dependencies due to memory/storage accesses
        """
        graph = nx.DiGraph()

        for instr in self._user_instr:
            instr_id = instr['id']
            graph.add_node(instr_id)

            for stack_elem in instr['inpt_sk']:
                # This means the stack element corresponds to another uninterpreted instruction
                associated_instr = self._var2instr.get(stack_elem, None)
                if associated_instr and not cheap(associated_instr):
                    graph.add_edge(instr_id, self._var2id[stack_elem])

        # We need to consider also the order given by the tuples
        for id1, id2 in self._deps:
            graph.add_edge(id2, id1)

        return graph

    def _condense_graph(self, dep_graph: nx.DiGraph) -> nx.DiGraph:
        """
        Given the complete dependency graph and the final stack, condenses all nodes so that only relevant memory
        instructions and stack elements in the final stack are left.
        """
        condensed_graph = nx.DiGraph()
        root_nodes = [node for node in dep_graph.nodes if dep_graph.in_degree(node) == 0]
        visited = dict()
        for root in root_nodes:
            self._condense_tree(root, visited, condensed_graph, dep_graph, True)
        return condensed_graph

    def _condense_tree(self, node, visited: Dict[str, Set[str]], condensed_graph: nx.DiGraph,
                       dep_graph: nx.DiGraph, is_root: bool = False) -> Set[str]:
        """
        Condenses the
        """
        successors = list(dep_graph.successors(node))
        if not successors:
            # Leaf node: just update the visited
            node_relevant = set()
            if self._is_relevant_instr(node):
                node_relevant.add(node)
                condensed_graph.add_node(node)
            visited[node] = node_relevant
            return node_relevant

        relevant_nodes = set()
        for successor in successors:
            relevant_successor = visited.get(successor, None)
            if relevant_successor is not None:
                relevant_nodes.update(relevant_successor)
            else:
                relevant_nodes.update(self._condense_tree(successor, visited, condensed_graph, dep_graph))

        # Once we have all the relevant nodes from the successors, we distinguish whether the current node
        # is relevant or not
        if self._is_relevant_instr(node) or is_root:
            condensed_graph.add_node(node)
            # We add a graph from each node of the relevant successors to the current one
            for relevant_node in relevant_nodes:
                condensed_graph.add_edge(node, relevant_node)

            visited[node] = {node}
            return {node}
        else:
            # Otherwise, we just assign the relevant nodes to the current node
            visited[node] = relevant_nodes
            return relevant_nodes

    def _is_relevant_instr(self, node):
        """
        Whether to consider the instruction associated to the node
        """
        instr = self._id2instr[node]
        return instr["storage"] or len(instr["outpt_sk"]) > 1 or \
            any(self._stack_var_copies_needed[out_stack] > 1 or out_stack in self._final_stack
                for out_stack in instr["outpt_sk"])

    def _generate_dataflow_tree_instr(self, original_instr_id: instr_id_T, instr: instr_JSON_T, term_graph: nx.DiGraph(),
                                      relevant_nodes: Set[instr_id_T]):
        instr_id = instr["id"]
        term_graph.add_node(instr_id, commutative=instr["commutative"])
        for i, input_var in enumerate(instr["inpt_sk"]):
            subterm = self._var2instr.get(input_var, None)
            if subterm is not None and subterm["id"] not in relevant_nodes:
                term_graph.add_edge(instr_id, subterm["id"], position=i)
                self._generate_dataflow_tree_instr(original_instr_id, subterm, term_graph, relevant_nodes)
            else:
                term_graph.add_edge(instr_id, input_var, position=i)

    def _generate_dataflow_tree(self, relevant_nodes: Set[instr_id_T]):
        """
        Generates a dataflow tree of a given node, considering only instructions that are not relevant
        """
        generated_graphs = dict()
        for relevant_node in relevant_nodes:
            instr = self._id2instr[relevant_node]
            instr_graph = nx.MultiDiGraph()
            self._generate_dataflow_tree_instr(instr["id"], instr, instr_graph, relevant_nodes)
            generated_graphs[relevant_node] = instr_graph
            # nx.nx_agraph.write_dot(instr_graph, relevant_node + ".dot")
        return generated_graphs

    def _max_n_elements_from_tree(self, dataflow_tree_dict: Dict[str, nx.DiGraph]):
        max_stack_size = dict()
        for relevant_node, tree in dataflow_tree_dict.items():
            max_stack_size[relevant_node] = compute_max_n_elements(relevant_node, tree)[0]
        return max_stack_size

    def _compute_top_can_used(self, instr: instr_JSON_T, top_can_be_used: Dict[var_id_T, Set[var_id_T]]) -> Set[
        var_id_T]:
        """
        Computes for each instruction if the topmost element of the stack can be reused directly
        at some point. It considers commutative operations
        """
        reused_elements = top_can_be_used.get(instr["id"], None)
        if reused_elements is not None:
            return reused_elements

        current_uses = set()
        comm = instr["commutative"]
        first_element = True
        for stack_var in reversed(instr["inpt_sk"]):
            # We only consider the first element if the operation is not commutative, or both elements otherwise
            if comm or first_element:
                instr_bef = self._var2instr.get(stack_var, None)
                if instr_bef is not None:
                    instr_bef_id = instr_bef["id"]
                    if instr_bef_id not in top_can_be_used:
                        current_uses.update(self._compute_top_can_used(instr_bef, top_can_be_used))
                    else:
                        current_uses.update(top_can_be_used[instr_bef_id])
                # Add only instructions that are relevant to our context
                current_uses.add(stack_var)
            else:
                break
            first_element = False

        top_can_be_used[instr["id"]] = current_uses
        return current_uses

    def greedy(self):
        """
        Initial call to recursive greedy
        """
        cstate: SymbolicState = self._initialize_initial_state()
        return self._greedy_recursive(cstate, self._final_stack)

    def _greedy_recursive(self, cstate: SymbolicState, target_stack: List[var_id_T], compute_all: bool = True) -> Tuple[List[instr_id_T], SymbolicState]:
        """
        Main implementation of the greedy algorithm (i.e. the instruction scheduling algorithm)
        """
        optg = []

        self.debug_logger.debug_initial(cstate.dep_graph.nodes)

        # Whether we are computing an element that is very deep and we must compute everything
        self.must_compute_all = False

        # We check the stack and the target stack are the same (up until the size of the target stack)
        # and all computations have been performed (optional, to allow recursive calls)
        while compute_all or cstate.stack[:len(target_stack)] != target_stack:
            var_top = cstate.top_stack()

            self.debug_logger.debug_loop(cstate.dep_graph, optg, cstate)
            self.debug_logger.debug_message(self.name)

            # Case 1: Top of the stack must be removed, as it appears more time it is being used
            if var_top is not None and cstate.stack_var_copies_needed[var_top] < 0:
                self.debug_logger.debug_pop(var_top, cstate)
                optg.extend(cstate.pop())

            # Case 2: Top of the stack must be placed in some other position
            elif (var_top is not None and (move_information := self.var_must_be_moved(var_top, cstate))
                  and move_information[0]):
                self.debug_logger.debug_move_var(var_top, move_information[1], cstate)
                optg.extend(cstate.swap(move_information[1]))

            # Case 3: Top of the stack cannot be moved to the corresponding position.
            # Hence, we just generate the following computation
            else:
                # There are no operations left to choose, so we stop the search
                if not cstate.has_computations():
                    break

                next_id, how_to_compute = self.choose_next_computation(cstate)
                self.debug_logger.debug_choose_computation(next_id, how_to_compute, cstate)

                if how_to_compute == "instr":
                    next_instr = self._id2instr[next_id]

                    # For more than two inputs, we recursively call the greedy algorithm
                    # with the input we want to obtain
                    if len(next_instr["inpt_sk"]) > 2:
                        ops = self._handle_recursive_case(cstate, next_instr)
                    else:
                        ops = self.compute_instr(next_instr, self.fixed_elements, cstate)

                elif how_to_compute == "deep":
                    # We must compute all elements and place it in their position
                    self.must_compute_all = True
                    ops = []

                elif how_to_compute == "swap":
                    # We need to find the first occurrence not solved of the variable
                    # and swap the topmost element
                    ops = cstate.swap(next_id)

                else:
                    ops = self.compute_var(next_id, cstate.positive_idx2negative(-1), cstate)

                optg.extend(ops)

        if compute_all:
            optg.extend(self.solve_permutation(cstate))
            self.debug_logger.debug_after_permutation(cstate, optg)

            self.print_traces(cstate)
            cstate.update_final_reachable(len(optg))

        return optg, cstate

    def _initialize_initial_state(self) -> SymbolicState:
        return SymbolicState(self._initial_stack, self._condensed_graph, self._relevant_nodes, self._stack_var_copies_needed,
                             self._user_instr, self._final_stack)

    def _available_positions(self, var_elem: var_id_T, cstate: SymbolicState) -> Generator[cstack_pos_T, None, None]:
        """
        Generator for the set of available positions in cstack where the var element can be placed
        """
        # We just need to check that the positions in which the element appears in the
        # final stack are in range and not contain the element
        for position in reversed(self._var2pos_stack[var_elem]):
            self.debug_logger.debug_message(f"{var_elem} Position {position}")
            fidx = idx_wrt_cstack(position, cstate.stack, self._final_stack)

            # When the index is negative, it means there are not enough elements in cstack
            # to place the corresponding element
            if fidx < 0:
                break

            # A variable must be moved when a positive index is found (less than STACK_DEPTH)
            # which does not contain yet the corresponding element
            elif min(len(cstate.stack), STACK_DEPTH) >= fidx >= 0 and cstate.stack[fidx] != var_elem:
                self.debug_logger.debug_message(f"{fidx}")

                yield fidx

    def _deepest_position(self, var_elem: var_id_T) -> Optional[int]:
        """
        Deepest position in the final stack of var_elem (if any). Used to determine which computation is chosen first
        """
        return self._var2pos_stack[var_elem][-1] if len(self._var2pos_stack[var_elem]) > 0 else None

    def var_must_be_moved(self, var_elem: var_id_T, cstate: SymbolicState) -> Tuple[bool, int]:
        """
        By construction, a var element must be moved if there is an available position in which it
        appears in the final stack (and it is not yet in its position). Return whether it is possible to
        perform the movement and the position the var element must be placed
        """
        topmost_idx_fstack = idx_wrt_fstack(0, cstate.stack, self._final_stack)
        # Condition: the topmost element is not placed in its corresponding position yet
        if topmost_idx_fstack < 0 or self._final_stack[topmost_idx_fstack] != var_elem:
            # Find the first position to which it can be moved
            next_available_pos = next(self._available_positions(var_elem, cstate), None)
            return next_available_pos is not None, next_available_pos
        return False, -1

    def choose_next_computation(self, cstate: SymbolicState) -> Tuple[Union[instr_id_T, var_id_T], str]:
        """
        Returns either a stack element or an instruction that must be computed
        """
        candidate_name, candidate_type, pos_to_place = self._select_candidate(cstate)

        if pos_to_place is not None:
            self.fixed_elements = pos_to_place
        else:
            # There are no fixed elements if it must not be placed in a concrete place
            self.fixed_elements = -1

        return candidate_name, candidate_type

    def _select_candidate(self, cstate: SymbolicState) -> Tuple[Union[instr_id_T, var_id_T], str, Optional[int]]:
        """
        Decides which stack variable or instruction must be computed using a scoring system
        """
        not_dependent_candidates, cheap_stack_elems, dup_stack_elems = cstate.candidates()

        best_candidate_score = 0,
        best_candidate_position = None
        candidate = None
        option = None

        # Only handle too deep choosing elements when we are not computing
        # a deep element
        if not self.must_compute_all:
            option = self._handle_too_deep(cstate)

        # First case: too deep scenario
        if option is not None:
            return option

        most_deps = 0
        # First, we evaluate the remaining instructions
        for id_ in not_dependent_candidates:
            score_id, pos_to_place = self._score_instr(self._id2instr[id_], cstate)

            n_deps = cstate.dep_graph.in_degree(id_) if id_ in cstate.dep_graph else 0

            # To decide whether the current candidate is the best so far, we use the information from deepest_pos
            # and reuses_pos. Moreover, in case of a tie, we choose an element that has the most dependencies
            better_candidate = score_id > best_candidate_score or \
                               (score_id == best_candidate_score and most_deps < n_deps)

            self.debug_logger.debug_message(f"{id_} {n_deps} {better_candidate}")
            if better_candidate:
                candidate = id_
                best_candidate_score = score_id
                best_candidate_position = pos_to_place
                most_deps = n_deps

            self.debug_logger.debug_rank_candidates(id_, score_id, better_candidate)

        # If the best candidate does not reuse the topmost element,
        # we also try duplicating already existing elements or cheap computations
        # from the bottom of the stack
        if candidate is None or best_candidate_score[0] == 0:

            associated_stack_var = None

            # First try: take the deepest position not solved
            if len(cstate.not_solved) > 0:
                deepest_position_not_solved = max(cstate.not_solved)

                associated_stack_var = self._final_stack[deepest_position_not_solved]
                if associated_stack_var in cheap_stack_elems or associated_stack_var in dup_stack_elems:
                    return associated_stack_var, "var", None

                elif (instr_id := self._var2id.get(associated_stack_var)) is not None \
                        and instr_id in not_dependent_candidates:
                    return instr_id, "instr", cstate.positive_idx2negative(-1)

            # Second try: choose the candidate we have
            if candidate is not None:
                return candidate, "instr", best_candidate_position

            swap_configuration = None
            # Check all positions that have not been solved yet
            for deepest_position_not_solved in sorted(cstate.not_solved, reverse=True):

                # Only within the current stack
                current_stack_idx = cstate.idx_wrt_cstack(deepest_position_not_solved)

                if current_stack_idx < -1:
                    break

                associated_stack_var = self._final_stack[deepest_position_not_solved]

                # Duplicate the element
                if associated_stack_var in cheap_stack_elems or associated_stack_var in dup_stack_elems:
                    return associated_stack_var, "var", None

                # The element has not been computed
                elif (instr_id := self._var2id.get(associated_stack_var)) is not None \
                        and instr_id in not_dependent_candidates:
                    return instr_id, "instr", cstate.positive_idx2negative(-1)

                # Third case: if there is no possibility left, we just swap an unsolved element
                elif swap_configuration is not None and (topmost := cstate.top_stack() is not None) and topmost != associated_stack_var:
                    swap_configuration = cstate.idx_wrt_cstack(deepest_position_not_solved), "swap", None

            # Just choose one element, as there is no clear alternative
            if len(not_dependent_candidates) > 0:
                return not_dependent_candidates[0], "instr", cstate.positive_idx2negative(-1)

            # Otherwise, we force an element to appear in top of the stack
            elif swap_configuration is not None:
                return swap_configuration

            assert candidate is not None, "This case should not happen"

        return candidate, "instr", best_candidate_position

    def _handle_too_deep(self, cstate: SymbolicState) -> Optional[Tuple[Union[instr_id_T, var_id_T], str, Optional[cstack_pos_T]]]:
        new_instr, cheap_stack_elems, dup_stack_elems = cstate.candidates()

        # All elements are placed in their corresponding position
        if len(cstate.not_solved) == 0:
            return None

        # First, we detect if there is an element that is about to become unreachable (and prioritize computing
        # this element)
        max_not_solved_pos = cstate.idx_wrt_cstack(cstate.max_solved - 1)

        if max_not_solved_pos >= STACK_DEPTH:
            # We try to compute the corresponding element in the deepest position
            return None

        elif STACK_DEPTH - 2 <= max_not_solved_pos <= STACK_DEPTH:
            # Returns either the instruction (if not computed yet) or the stack variable
            # of the stack element associated to the instruction
            final_stack_var = self._final_stack[max_not_solved_pos]

            if final_stack_var in dup_stack_elems:
                return final_stack_var, "var", None

            elif final_stack_var in cheap_stack_elems or cstate.dep_graph.out_degree(self._var2instr[final_stack_var]) == 0:
                instr = self._var2instr[final_stack_var]
                _, initial_position = self.decide_fixed_elements(cstate, instr)
                return instr["id"], "instr", initial_position

            else:
                return None

        return None

    def _score_instr(self, instr: instr_JSON_T, cstate: SymbolicState) -> Tuple[Tuple, int]:
        """
        We score the instructions according to the following lexicographic order:
        1) Number of elements that can be reused

        Moreover, we return the position from which to start computing
        """
        n_reused, initial_position = self.decide_fixed_elements(cstate, instr)

        return (n_reused, ), initial_position

    def compute_instr(self, instr: instr_JSON_T, position_to_start_computing: cstack_pos_T,
                      cstate: SymbolicState, depth: int = 0) -> List[instr_id_T]:
        """
        Given an instr, the (negative) position in which it is being started computed and the current state,
        computes the corresponding term. This function is separated from compute_var because there
        are terms, such as var accesses or memory accesses that produce no var element as a result.
        """
        self.debug_logger.debug_compute_instr(instr, position_to_start_computing, cstate, depth)

        seq = []

        # Decide in which order computations must be done (after computing the subterms)
        input_vars = self._computation_order(instr, position_to_start_computing, cstate)
        self.debug_logger.debug_message(f"Fixed elements {self.fixed_elements} {cstate}", depth)

        for i, stack_var in enumerate(input_vars):
            # The initial index is negative
            # We have to consider the negative position in which we want to compute current element
            position_to_place = position_to_start_computing - i
            self.debug_logger.debug_message(f"Position to place {position_to_place}", depth)

            # First case: the element is already placed in their position, and either it is not used elsewhere
            # or we already have a copy or it is cheap to compute (i.e. there is an element that can be reused)
            if cstate.is_in_negative_range(position_to_place) and cstate.stack[position_to_place] == stack_var and \
                    (((var_instr := self._var2instr.get(stack_var)) is not None and cheap(var_instr)) or cstate.var_elem_can_be_reused(stack_var, cstate.negative_idx2positive(self.fixed_elements))):
                pass
            else:
                # Otherwise, we must return generate the element it with a recursive call
                seq.extend(self.compute_var(stack_var, position_to_place, cstate, depth + 1))

        # Finally, we compute the element
        seq.extend(cstate.uf(instr))

        return seq

    def _must_be_reversed(self, instr: instr_JSON_T, start_position: cstack_pos_T,
                           cstate: SymbolicState):
        """
        Checks whether the arguments for a computation must be reversed or not
        """
        if instr['commutative'] and -len(cstate.stack) <= start_position:
            # If it's commutative, study its dependencies.
            if self.debug_mode:
                assert len(instr['inpt_sk']) == 2, \
                    f'Commutative instruction {instr["id"]} has arity != 2'

            # Condition: the top of the stack can be reused
            first_consumed_element = cstate.stack[start_position]
            first_arg_instr = self._var2instr.get(instr['inpt_sk'][0], None)

            # Condition1: the topmost element can be reused by the first argument instruction or is the first argument
            condition1 = (first_consumed_element is not None and first_consumed_element in self._top_can_be_used[instr["id"]] and
                          first_arg_instr is not None and (first_arg_instr["outpt_sk"][0] == first_consumed_element or
                                                           first_consumed_element in self._top_can_be_used[first_arg_instr["id"]]))

            # Condition2: the first argument just needs to be swapped
            condition2 = cstate.stack_var_copies_needed[instr['inpt_sk'][0]] == 0
            return condition1 or condition2
        return False

    def _computation_order(self, instr: instr_JSON_T, start_position: cstack_pos_T,
                           cstate: SymbolicState) -> List[var_id_T]:
        """
        Decides in which order the arguments of the instruction must be computed
        """
        self.debug_logger.debug_message(f"{start_position} {len(cstate.stack)}")
        if self._must_be_reversed(instr, start_position, cstate):
                input_vars = instr['inpt_sk']
        else:
            input_vars = list(reversed(instr['inpt_sk']))

        return input_vars

    def decide_fixed_elements(self, cstate: SymbolicState, instr: instr_JSON_T) -> Tuple[int, cstack_pos_T]:
        """
        Decides from which position in the current stack we are computing the arguments of the corresponding element,
        expressed in a negative index (from the bottom). Assumes the input vars are given from top to bottom
        """
        # TODO: (possibly) combine with computation order and make it more efficient based on KMP
        input_vars = instr["inpt_sk"]
        best_possibility = 0
        best_idx = cstate.positive_idx2negative(-1)

        # The value from instr2max_n_elems stores the maximum number of elements
        # that can appear in the stack in order to apply an operation
        max_idx = min(len(input_vars) - 1, self._instr2max_n_elems[instr["id"]] - 1,
                      cstate.idx_wrt_cstack(cstate.max_solved - 1))
        count = 0
        idx = 0
        matching = True

        # We only consider elements until some of them need to be copied
        while matching and max_idx >= idx:
            stack_idx, input_idx, count = idx, len(input_vars) - 1, 0
            while matching and stack_idx >= 0 and input_idx >= 0:
                # We can reuse the element
                # Only consider elements until some of them cannot be swapped
                if cstate.stack_var_copies_needed[input_vars[input_idx]] == 0:
                    if cstate.stack[stack_idx] == input_vars[input_idx]:
                        count += 1
                    input_idx -= 1
                    stack_idx -= 1
                else:
                    matching = False

            # We try to swap as much elements as possible
            if matching and count > best_possibility:
                best_idx = cstate.positive_idx2negative(idx)
                best_possibility = count

            idx += 1

        # Last possibility: check if the topmost element can be reused
        # according top_can_be_used
        if count == 0:
            top = cstate.top_stack()
            if top is not None and top in self._top_can_be_used[instr["id"]] \
                    and cstate.stack_var_copies_needed[top] == 0:
                return 1, cstate.positive_idx2negative(0)

        return count, best_idx

    def compute_var(self, var_elem: var_id_T, position_to_place: cstack_pos_T, cstate: SymbolicState,
                    depth: int = 0) -> List[instr_id_T]:
        """
        Given a stack_var, a negative position and current state, computes the element and places it in its
        corresponding position, updating the cstate accordingly. Returns the sequence of ids. Compute var considers
        it the var elem is already stored in the stack
        """
        self.debug_logger.debug_compute_var(var_elem, position_to_place, cstate, depth)
        # First, we compute the element we need if needed

        # First case: the element has not been computed previously. We have to compute it, as it
        # corresponds to a stack variable
        instr = self._var2instr.get(var_elem, None)

        if instr is not None and (cstate.n_computed[var_elem] == 0 or cheap(instr)) and cstate.stack_var_copies_needed[var_elem] > 0:
            # First we compute the instruction
            seq = self.compute_instr(instr, position_to_place, cstate, depth + 1)

        # Second case: the variable has already been computed (i.e. var_uses > 0).
        # In this case, we duplicate it or retrieve it from memory
        else:
            assert var_elem in cstate.stack, f"Variable {var_elem} must appear in the stack, " \
                                             f"as it was previously computed and it is not a cheap computation"
            # TODO: case for recomputing the element?

            # Case I: We swap the element the number of copies required is met or we have enough copies,
            # the position is accessible and it is not already part of the fixed size of the stack
            position_reusing = cstate.position_to_swap(var_elem, cstate.negative_idx2positive(self.fixed_elements))
            self.debug_logger.debug_message(f"Reusing: {position_reusing} {var_elem}")
            # Subcase I.1: we can have enough elements to perform the swap
            if position_reusing != -1 and cstate.is_in_negative_range(position_to_place):

                # We swap to the deepest accesible copy
                seq = cstate.swap(position_reusing)
                self.debug_logger.debug_message(f"SWAP{position_reusing} {cstate.stack}")

            # Subcase I.2: there is an element to use for duplicating and then swapping. We only
            # consider positions till the final stack, as they must be swapped at some point
            elif position_reusing != -1 and cstate.elements_to_dup() > 0 and position_to_place >= - len(cstate.final_stack):
                assert position_to_place == -len(cstate.stack) - 1, f"Position to place {position_to_place} is " \
                                                                    f"not coherent in stack {cstate}"

                # TODO: decide how which computation to duplicate
                other_var_elem = self.intermediate_op_to_compute(cstate)
                assert other_var_elem is not None, "No other element can be duplicated at this point"

                self.debug_logger.debug_message(f"Other stack var element: {other_var_elem}", depth)
                idx = cstate.first_occurrence(other_var_elem) + 1
                seq = cstate.dup(idx)
                self.debug_logger.debug_message(f"Computing other element to SWAP: DUP{idx} {cstate.stack}", depth)

                # Afterwards, we swap the element we have computed (considering we have added an extra element)
                # Strange case: we might just have computed the element we needed
                seq.extend(cstate.swap(position_reusing + 1))

            # Case II: we duplicate the element that is within reach
            elif cstate.is_accessible_dup(var_elem):
                idx = cstate.first_occurrence(var_elem) + 1
                seq = cstate.dup(idx)
                self.debug_logger.debug_message(f"DUP{idx} {cstate.stack}", depth)

            # Case III: we retrieve the element from memory
            else:
                seq = cstate.from_memory(var_elem, True)

        # Finally, we place the topmost element that has been computed in the position to place
        # TODO: case for multiple elements computed
        self.debug_logger.debug_message(f"Pos {position_to_place}")
        if cstate.is_in_negative_range(position_to_place) and cstate.stack[position_to_place] != var_elem:
            assert cstate.top_stack() == var_elem, f"Var elem {var_elem} must be placed on top of the stack"
            positive_idx_to_place = cstate.negative_idx2positive(position_to_place)
            seq.extend(cstate.swap(positive_idx_to_place))
            self.debug_logger.debug_message(f"SWAP{positive_idx_to_place} {cstate.stack}", depth)

        return seq

    def intermediate_op_to_compute(self, cstate: SymbolicState) -> Optional[var_id_T]:
        """
        Computes an intermediate computation that only increases by one the length
        """
        _, cheap_instrs, dup_stack_vars = cstate.candidates()

        # First we try elements that must be duplicated
        # TODO: better heuristics for choosing the intermediate operation
        for stack_var in dup_stack_vars:
            self.debug_logger.debug_message(f"Considered var element: {stack_var}")

            if cstate.is_accessible_dup(stack_var):
                return stack_var

        return None

    def _elements_needed(self, instr_: instr_JSON_T, cstate: SymbolicState, n_elements: Counter[var_id_T]) -> None:
        """
        Stores how many times stack vars are needed
        to compute instr in n_elements according to cstate
        """
        for input_var in instr_["inpt_sk"]:
            instr = self._var2instr.get(input_var)
            # If a stack variable has not been computed,
            # we recursively invoke the instruction
            if instr is not None and instr["id"] not in cstate.computed:
                self._elements_needed(instr, cstate, n_elements)
            else:
                n_elements.update([input_var])

    def _combine_operands_and_stack(self, cstate: SymbolicState, input_vars: List[var_id_T],
                                    elements_needed: Counter[var_id_T]):
        """
        Combines the operands from the instruction to which compute the
        recursive greedy and the input stack to ensure values that must be
        """
        new_stack = []
        # First detect which elements should not appear anymore
        # due to being consumed when computing the recursive function
        for var_ in cstate.stack:

            # If the number it is computed in the stack + the number of times
            # it stills needs to be computed correspond to the elements needed, then
            # we have to remove that element
            diff = cstate.n_computed[var_] + cstate.stack_var_copies_needed[var_] - elements_needed.get(var_, 0)
            if diff == 0:
                new_stack.append(None)
            else:
                assert diff > 0, f"n_computed + stack_var_copies_needed must be >= elements to compute for {var_}"
                new_stack.append(var_)

        i, j = 0, len(new_stack) - 1
        while i <= j:
            if new_stack[i] is None:
                i += 1
            elif new_stack[j] is None:
                new_stack[j] = new_stack[i]
                i += 1
                j -= 1
            else:
                j -= 1

        return input_vars + new_stack[i:]


    def _handle_recursive_case(self, cstate: SymbolicState, next_instr: instr_JSON_T):
        """
        Given the instruction for which we want to find the input stack,
        we prepare the call to return the ops
        """

        # The new final stack adds the element we want to compute to the top
        old_stack = self._final_stack
        old_var2pos = self._var2pos_stack

        elements_needed = Counter()
        self._elements_needed(next_instr, cstate, elements_needed)

        new_final_stack = self._combine_operands_and_stack(cstate, next_instr["inpt_sk"], elements_needed)
        self.debug_logger.debug_message(f"Final stack {new_final_stack}")

        new_relevant = set(instr["id"] for final_var in next_instr["inpt_sk"]
                           if final_var not in self._relevant_nodes and
                           (instr := self._var2instr.get(final_var)) is not None and not cheap(instr))

        # We prepare the state for the recursive greedy
        cstate.recursive_state(next_instr, new_final_stack, new_relevant)

        self._final_stack = new_final_stack
        self._var2pos_stack = self._compute_var2pos(self._final_stack)

        # Call the greedy without that instruction
        opts_rec, _ = self._greedy_recursive(cstate, new_final_stack, False)

        self._final_stack = old_stack
        self._var2pos_stack = old_var2pos

        # Restore the state to compute the instruction afterwards
        cstate.restore_state()

        self.fixed_elements = cstate.positive_idx2negative(len(next_instr["inpt_sk"]) - 1)
        ops = self.compute_instr(next_instr, self.fixed_elements, cstate)
        return opts_rec + ops

    def solve_permutation(self, cstate: SymbolicState) -> List[instr_id_T]:
        """
        Places all the elements in their corresponding positions, after having
        computing every element. Note that we might need to remove some elements
        (if they were not accessible to be removed).
        """
        # TODO: complete code
        permutation_ops = []

        # Previous step: if the deepest element that is not placed in its correct position cannot
        # be reached directly, we have to make enough room to access it. This only needs to be done once
        # (as subsequent elements that must be placed are more shallow)
        self.debug_logger.debug_message(f"{cstate.max_solved - 1}")
        if cstate.max_solved - 1 > STACK_DEPTH:
            permutation_ops.extend(self.reach_position_stack(cstate, cstate.max_solved - 1))

        while cstate.stack != self._final_stack:
            topmost_element = cstate.top_stack()
            assert topmost_element is not None, "Topmost element cannot be None in solve permutation"

            # First case: pop the element
            if cstate.stack_var_copies_needed[topmost_element] < 0:
                permutation_ops.extend(cstate.pop())

            else:
                # Second case: there is a position in which the element must appear
                misplaced = False
                for position_available in self._available_positions(topmost_element, cstate):
                    # Search for an available position in which the element is not already there
                    if cstate.stack[position_available] != topmost_element:
                        misplaced = True
                        break

                if misplaced:
                    permutation_ops.extend(cstate.swap(position_available))

                else:
                    assert cstate.idx_wrt_cstack(cstate.max_solved - 1) <= STACK_DEPTH, \
                        "Solve Permutation loop has all elements within reach"

                    # Third case: we need to load the element from the memory if it is not already in the stack
                    last_misplaced_element = self._final_stack[cstate.max_solved - 1]
                    if last_misplaced_element not in cstate.stack:
                        permutation_ops.extend(cstate.from_memory(last_misplaced_element, False))

                    # Forth case: just swap current element with the element at max_solved, as that one is misplaced
                    else:
                        permutation_ops.extend(cstate.swap(cstate.idx_wrt_cstack(cstate.max_solved - 1)))

        return permutation_ops

    def reach_position_stack(self, cstate: SymbolicState, final_position: fstack_pos_T) -> List[instr_id_T]:
        """
        Stores elements in memory in order to make space for the stack. Otherwise, it stores elements in the memory.
        """

        # First we try to pop the unused elements in the stack
        pop_elements = self.pop_unused_elements(cstate)

        # Let's see if trying to store unused elements is enough to reach that position
        current_position = cstate.idx_wrt_cstack(final_position)
        if len(pop_elements) > 0 and current_position <= STACK_DEPTH:
            return pop_elements

        store_memory = self.move_vars_to_memory(current_position, cstate)
        return pop_elements + store_memory

    def pop_unused_elements(self, cstate: SymbolicState) -> List[instr_id_T]:
        """
        Scans the current stack trying to remove all unnecessary elements
        """
        current_idx = 0
        var_top = cstate.top_stack()
        if var_top is None:
            return []

        pop_ops = []

        while current_idx <= min(STACK_DEPTH, len(cstate.stack)):

            if cstate.stack_var_copies_needed[cstate.stack[current_idx]] < 0:
                # First swap the corresponding element
                if current_idx > 0:
                    pop_ops.extend(cstate.swap(current_idx))

                pop_ops.extend(cstate.pop())
            else:
                current_idx += 1

        return pop_ops

    def move_vars_to_memory(self, current_position: cstack_pos_T, cstate: SymbolicState) -> List[instr_id_T]:
        """
        Stores variables in memory in order to make enough space to reach element in "current_position"
        """
        # TODO: better heuristics?
        move_vars_ops = []

        # There are two options: if the memory contains the corresponding element, then we store an extra element
        # to be able to load it from memory
        element_in_position = self._final_stack[cstate.idx_wrt_fstack(current_position)]
        stored_in_memory = self._final_stack[cstate.idx_wrt_fstack(current_position)] in cstate.vars_in_memory

        while current_position > STACK_DEPTH or (current_position == STACK_DEPTH and stored_in_memory):
            topmost_element = cstate.top_stack()

            # The elements we are storing could be the one we will have to swap
            if topmost_element == element_in_position:
                stored_in_memory = True

            move_vars_ops.extend(cstate.store_in_memory())
            current_position -= 1

        return move_vars_ops

    def print_traces(self, cstate: SymbolicState) -> None:
        """
        Prints the traces so far from the current state. Debug mode must be activated
        """
        if cstate.debug_mode:
            list_strings = [str(t[0]) for t in cstate.trace]
            max_list_len = max(len(ls) for ls in list_strings)

            # Calculate the maximum length of the string part
            max_str_len = max(len(t[1]) for t in cstate.trace)

            # Print each tuple with aligned formatting
            for (lst, string), list_str in zip(cstate.trace, list_strings):
                print(f"{string:<{max_str_len}} {list_str:>{max_list_len}}")


class DebugLogger:
    """
    Class that contains the multiple debugging messages for the greedy algorithm
    """

    def __init__(self):
        self._logger = logging.getLogger("greedy")

    def debug_initial(self, ops: List[instr_id_T]):
        self._logger.debug("---- Initial Ops ----")
        self._logger.debug(f'Ops:{ops}')
        self._logger.debug("")

    def debug_loop(self, dep_graph, optg: List[instr_id_T],
                   cstate: SymbolicState):
        self._logger.debug("---- While loop ----")
        self._logger.debug(f"Ops not computed {cstate.relevant_nodes}")
        self._logger.debug(f"Ops computed: {optg}")
        self._logger.debug(cstate)
        self._logger.debug(cstate.max_solved)
        self._logger.debug("")

    def debug_pop(self, var_top: var_id_T, cstate: SymbolicState):
        self._logger.debug("---- Drop term ----")
        self._logger.debug(f"Var Term: {var_top}")
        self._logger.debug(f'State {cstate}')
        self._logger.debug("")

    def debug_move_var(self, var_top: var_id_T, position: int, cstate: SymbolicState):
        self._logger.debug("---- Move var to position ----")
        self._logger.debug(f"Var Term: {var_top}")
        self._logger.debug(f"Position: {position}")
        self._logger.debug(f'State {cstate}')
        self._logger.debug("")

    def debug_rank_candidates(self, candidate: instr_id_T, candidate_score: Tuple[bool, Dict[var_id_T, int]],
                              chosen: bool):
        self._logger.debug("---- Score candidate ----")
        self._logger.debug(f"Candidate {candidate}")
        self._logger.debug(f'Candidate score {candidate_score}')
        self._logger.debug("Candidate has been chosen" if chosen else "Candidate does not improve")
        self._logger.debug("")

    def debug_choose_computation(self, next_id: instr_id_T, how_to_compute: str, cstate: SymbolicState):
        self._logger.debug("---- Computation chosen ----")
        self._logger.debug(f"Computation method {how_to_compute}")
        self._logger.debug(next_id)
        self._logger.debug(cstate)
        self._logger.debug("")

    def debug_compute_instr(self, instr: instr_JSON_T, position: cstack_pos_T, cstate: SymbolicState, depth: int = 0):
        INDENT = " " * 4 * depth
        self._logger.debug(f"{INDENT}---- Computing instr ----")
        self._logger.debug(f"{INDENT}{instr}")
        self._logger.debug(f"{INDENT}Position: {position}")
        self._logger.debug(f"{INDENT}Stack: {cstate.stack}")
        self._logger.debug(INDENT)

    def debug_compute_var(self, var: var_id_T, position: cstack_pos_T, cstate: SymbolicState, depth: int = 0):
        INDENT = " " * 4 * depth
        self._logger.debug(f"{INDENT}---- Computing variable ----")
        self._logger.debug(INDENT + var)
        self._logger.debug(f"{INDENT}Position: {position}")
        self._logger.debug(f"{INDENT}Stack: {cstate.stack}")
        self._logger.debug(INDENT)

    def debug_after_permutation(self, cstate: SymbolicState, optg: List[instr_id_T]):
        self._logger.debug("---- State after solving permutation ----")
        self._logger.debug(cstate)
        self._logger.debug(optg)
        self._logger.debug("")

    def debug_message(self, message: str, depth: int = 0):
        INDENT = " " * 4 * depth
        self._logger.debug(f"{INDENT}{message}")


def greedy_standalone(sms: Dict) -> GreedyInfo:
    """
    Executes the greedy algorithm as a standalone configuration. Returns whether the execution has been
    sucessful or not ("non_optimal" or "error"), the total time and the sequence of ids returned.
    """
    error = 0
    usage_start = resource.getrusage(resource.RUSAGE_SELF)
    try:
        seq_ids, cstate = SMSgreedy(sms).greedy()
        usage_stop = resource.getrusage(resource.RUSAGE_SELF)

        # We extract the information from the cstate, in which it is preserved
        get_count, elements_to_fix, reachable = cstate.get_count, cstate.elements_to_fix, cstate.reachable

    except Exception as e:
        usage_stop = resource.getrusage(resource.RUSAGE_SELF)
        _, _, tb = sys.exc_info()
        traceback.print_tb(tb)
        print(e, sms["name"], file=sys.stderr)
        error = 1
        seq_ids, get_count, elements_to_fix, reachable = [], dict(), set(), set()
    optimization_outcome = "error" if error == 1 else "non_optimal"
    return GreedyInfo.from_new_version(seq_ids, optimization_outcome,
                                       usage_stop.ru_utime + usage_stop.ru_stime - usage_start.ru_utime - usage_start.ru_stime,
                                       sms["user_instrs"], get_count, elements_to_fix, reachable)


def greedy_from_file(filename: str) -> Tuple[SMS_T, GreedyInfo]:
    logging.basicConfig(level=logging.DEBUG)
    with open(filename, "r") as f:
        sfs = json.load(f)
    return sfs, greedy_standalone(sfs)


if __name__ == "__main__":
    sfs, greedy_info = greedy_from_file(sys.argv[1])
    assert check_execution_from_ids(sfs, greedy_info.greedy_ids), "Not correct check"
