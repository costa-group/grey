#!/usr/bin/env python3
import itertools
import json
import sys
import os
from typing import List, Dict, Tuple, Any, Set, Optional
from collections import defaultdict, Counter
import traceback
from enum import Enum, unique

import networkx
import networkx as nx
from analysis.greedy_validation import check_execution_from_ids
from global_params.types import var_id_T, instr_id_T, instr_JSON_T


def idx_wrt_cstack(idx: int, cstack: List, fstack: List) -> int:
    """
    Given a position w.r.t fstack, returns the corresponding position w.r.t cstack
    """
    return idx - len(fstack) + len(cstack)


def idx_wrt_fstack(idx: int, cstack: List, fstack: List) -> int:
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
    return len(instr['inpt_sk']) == 0 and instr["inpt_sk"] <= 2


class SymbolicState:
    """
    A symbolic state includes a stack, and a dict indicating the number of total uses of each
    instruction
    """

    def __init__(self, stack: List[var_id_T]) -> None:
        self.stack: List[var_id_T] = stack

        # Var uses counts how many times the corresponding variables appears in the current stack
        self.var_uses: Dict[var_id_T, int] = self._computer_var_uses()

        self.debug_mode = True

    def _computer_var_uses(self):
        var_uses = defaultdict(lambda: 0)

        # Count vars in the initial stack
        for var_stack in self.stack:
            var_uses[var_stack] += 1

        return var_uses

    def swap(self, x: int) -> None:
        """
        Stores the top of the stack in the local with index x. in_position marks whether the element is
        solved in flocals
        """
        assert 0 <= x < len(self.stack), f"Swapping with index {x} a stack of {len(self.stack)} elements: {self.stack}"
        self.stack[0], self.stack[x] = self.stack[x], self.stack[0]

        # Var uses: no modification, as we are just moving two elements

    def dup(self, x: int) -> None:
        """
        Tee instruction in local with index x. in_position marks whether the element is solved in flocals
        """
        assert 0 <= x < len(self.stack), f"Duplicating index {x} in a stack in {len(self.stack)} elements: {self.stack}"
        self.stack.insert(0, self.stack[x])

        # Var uses: we increment the element that we have in its corresponding position
        self.var_uses[self.stack[0]] += 1

    def pop(self):
        """
        Drops the last element
        """
        stack_var = self.stack.pop(0)

        # Var uses: we subtract one because the stack var is totally removed from the encoding
        self.var_uses[stack_var] -= 1

    def uf(self, instr: instr_JSON_T):
        """
        Symbolic execution of instruction instr. Additionally, checks the arguments match if debug mode flag is enabled
        """
        consumed_elements = [self.stack.pop(0) for _ in range(len(instr['inpt_sk']))]

        # Neither liveness nor var uses are affected by consuming elements, as these elements are just being embedded
        # into a new term
        # Debug mode to check the pop args from the stack match
        if self.debug_mode:
            if instr['commutative']:
                # Compare them as multisets
                assert Counter(consumed_elements) == Counter(instr['inpt_sk']), \
                    f"{instr['id']} is not consuming the correct elements from the stack"
            else:
                # Compare them as lists
                assert consumed_elements == instr['inpt_sk'], \
                    f"{instr['id']} is not consuming the correct elements from the stack"

        # We introduce the new elements
        for output_var in instr['outpt_sk']:
            self.stack.insert(0, output_var)
            # Var uses: increase one for each generated stack var
            self.var_uses[output_var] += 1

        return instr['outpt_sk']

    def top_stack(self) -> Optional[var_id_T]:
        return None if len(self.stack) == 0 else self.stack[0]

    def __repr__(self):
        return str(self.stack)
