"""
Module that ensures every value stored in memory has a single definition before computing the
liveness and colouring (tree scan, see "SSA-based Compiler Design", Algorithm 22.1). After the
DUP-VSET placement, a variable v can be stored in memory in three ways:
  1. DUP-VSET(v, pos): at most once per variable, at a point that dominates all the VGETs of v that
     are not preceded by a VSET(v) in the same block.
  2. As a phi def in phi_defs_to_solve: the value is written by the copies at the end of the
     predecessors, so it is defined at the entry of its block.
  3. VSET(v): emitted by the greedy algorithm to make room in the stack. The following VGET(v) in
     the same block recover it.
A VSET(v) (resp. DUP-VSET) dominated by another definition of v is redundant, as in SSA the value
of v never changes: the VSET becomes a POP (it still has to remove v from the stack) and the
DUP-VSET is removed. Otherwise, a VSET starts a local range that only lives in its block: it is
renamed together with the VGETs that follow it, so that it has its own liveness and colour.
"""
from typing import Dict, List, Optional, Tuple

import networkx as nx

import global_params.constants as constants
from global_params.types import block_id_T, var_id_T
from parser.cfg_block_list import CFGBlockList
from reparation.utils import extract_value_from_pseudo_instr

# A definition point: the block and the index in its greedy ids (-1 for the entry of the block)
definition_point_T = Tuple[block_id_T, int]


def local_range_name(var: var_id_T, block_id: block_id_T, position: int) -> var_id_T:
    """
    Name of the local range started by a VSET(var) at the given position
    """
    return f"{var}@{block_id}#{position}"


class DominanceIntervals:
    """
    Preorder intervals of the dominator tree, to answer dominance queries in constant time
    """

    def __init__(self, dominator_tree: nx.DiGraph, root: block_id_T):
        self._entry: Dict[block_id_T, int] = {}
        self._exit: Dict[block_id_T, int] = {}
        counter = 0
        # Iterative DFS to avoid the recursion limit in big CFGs
        stack = [(root, False)]
        while stack:
            node, visited = stack.pop()
            if visited:
                self._exit[node] = counter
                continue
            self._entry[node] = counter
            counter += 1
            stack.append((node, True))
            for child in sorted(dominator_tree.successors(node), reverse=True):
                stack.append((child, False))

    def dominates(self, block1: block_id_T, block2: block_id_T) -> bool:
        """
        Whether block1 dominates block2 (reflexive)
        """
        if block1 not in self._entry or block2 not in self._entry:
            return False
        return self._entry[block1] <= self._entry[block2] and self._exit[block2] <= self._exit[block1]


def point_dominates(dominance: DominanceIntervals, point1: definition_point_T, point2: definition_point_T) -> bool:
    """
    Whether the program point point1 strictly precedes point2 in every path, i.e. point1 dominates point2
    """
    block1, position1 = point1
    block2, position2 = point2
    if block1 == block2:
        return position1 < position2
    return dominance.dominates(block1, block2)


def global_definitions(block_list: CFGBlockList) -> Dict[var_id_T, List[definition_point_T]]:
    """
    Collects the DUP-VSETs and the phi defs handled in memory of every variable
    """
    definitions: Dict[var_id_T, List[definition_point_T]] = {}
    for block_id, block in block_list.blocks.items():
        greedy_info = block.greedy_info
        for phi_def in sorted(greedy_info.phi_defs_to_solve):
            definitions.setdefault(phi_def, []).append((block_id, -1))
        for position, instr_id in enumerate(greedy_info.greedy_ids):
            if instr_id.startswith("DUP-VSET"):
                definitions.setdefault(extract_value_from_pseudo_instr(instr_id), []).append((block_id, position))
    return definitions


def ensure_single_definitions(block_list: CFGBlockList) -> int:
    """
    Removes the redundant stores and renames the local ranges started by a VSET, so that every value stored
    in memory has a single definition. Returns the number of redundant stores removed
    """
    dominance = DominanceIntervals(block_list.dominant_tree, block_list.start_block)
    definitions = global_definitions(block_list)

    # For each variable, the global definition that dominates the rest of them (if any). The DUP-VSETs
    # dominated by it are redundant
    main_definition: Dict[var_id_T, definition_point_T] = {}
    redundant_dup_vsets = set()
    for var, points in definitions.items():
        dominating = [point for point in points
                      if all(point == other or point_dominates(dominance, point, other) for other in points)]
        if constants.DEBUG:
            assert dominating, f"The global definitions of {var} do not dominate each other: {points}"
        if dominating:
            main_definition[var] = dominating[0]
            redundant_dup_vsets.update(point for point in points if point != dominating[0])

    num_redundant = 0
    for block_id, block in block_list.blocks.items():
        greedy_info = block.greedy_info
        new_greedy_ids = []
        # Current name of each variable accessed in memory in this block (local ranges)
        current_name: Dict[var_id_T, var_id_T] = {}
        for position, instr_id in enumerate(greedy_info.greedy_ids):
            if instr_id.startswith("DUP-VSET") and (block_id, position) in redundant_dup_vsets:
                # The value is already stored in memory: the DUP-VSET is not needed (stack neutral)
                num_redundant += 1
                continue

            if instr_id.startswith("VSET"):
                var = extract_value_from_pseudo_instr(instr_id)
                definition = main_definition.get(var)
                if definition is not None and point_dominates(dominance, definition, (block_id, position)):
                    # Already stored by a dominating definition: just remove it from the stack
                    new_greedy_ids.append("POP")
                    current_name.pop(var, None)
                    num_redundant += 1
                else:
                    # A local range starts here
                    current_name[var] = local_range_name(var, block_id, position)
                    new_greedy_ids.append(f"VSET({current_name[var]})")
                continue

            if instr_id.startswith("VGET"):
                var = extract_value_from_pseudo_instr(instr_id)
                if var in current_name:
                    new_greedy_ids.append(f"VGET({current_name[var]})")
                    continue
                if constants.DEBUG:
                    definition = main_definition.get(var)
                    assert definition is not None and point_dominates(dominance, definition, (block_id, position)), \
                        f"VGET({var}) in block {block_id} is not dominated by any store of {var}"

            new_greedy_ids.append(instr_id)

        # Stack-neutral changes: the reachability information (stack positions) is still valid
        greedy_info.greedy_ids = new_greedy_ids
    return num_redundant
