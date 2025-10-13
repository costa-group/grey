"""
Module that implements an alternative version the Tree Scan algorithm from
"SSA-based Compiler Design" (Page 309). The key difference is that we assume
an unbounded number of registers to colour, as the EVM memory can
grow indefinitely (although dangerously in cost...). Moreover, the liveness sets
are determined according to the last point in which a variable could be accessed
"""
import networkx as nx
from collections import defaultdict
from global_params.types import var_id_T, block_id_T, element_definition_T
from typing import List, Dict, Tuple, Set, Optional
from parser.cfg_block import CFGBlock
from parser.cfg_block_list import CFGBlockList
from graphs.cfg import compute_loop_nesting_forest_graph
from reparation.atomic_merged_sets import AtomicMergedSets


class ColourAssignment:
    """
    Class to represents the colouring of the graph.
    """

    def __init__(self, block_list: CFGBlockList, dominance_tree: nx.DiGraph,
                 ordered_program_points: Dict[block_id_T, List[int]],
                 atomic_merged_sets: AtomicMergedSets):
        # Parameters that are passed to colour the graph
        self._block_list = block_list
        self._dominance_tree = dominance_tree

        # Assigns the variables that are released by
        # the end of each branch in the tree
        self._ordered_program_points = ordered_program_points

        # Sets of variables that MUST contain the same colour
        self._atomic_merged_sets = atomic_merged_sets

        self._total_colors: int = 0
        self._used_colors: int = 0

        # We determine which variable is associated to a colour
        self._var2color: Dict[block_id_T, int] = dict()

        # Colors currently assigned
        self._assigned_colours: Set[var_id_T] = set()

    def _coalesce_resource(self, element_to_fix: element_definition_T):
        """
        Given a variable that is inaccessible and corresponds to a phi-function,
        coalesces it into a single resource
        """
        pass

    def initial_coalesce(self, elements_to_fix: Set[element_definition_T]):
        """
        Given the initial colour, coalesces all phi-related resources to the
        same common resource. The issue is later de-coalescing resources that interfere

        elements_to_fix: set of variables to fix and in which block they are defined.
        """
        pass
        # We only need to coalesce blocks that have common resources

    def _pick_colour(self, v: var_id_T, available: List[bool]):
        """
        Chooses an available colour, adding a new one if there are not enough
        """
        # We add v to the set of assigned colours
        self._assigned_colours.add(v)

        # If all colours are used, we need to increase the number of colours
        if self._total_colors == self._used_colors:
            self._total_colors += 1
            self._used_colors += 1
            available.append(False)
            self._var2color[v] = self._total_colors - 1
        else:
            i = 0
            found_colour = False
            while not found_colour and i < self._total_colors:
                if available[i]:
                    available[i] = False
                    found_colour = True
                    self._used_colors += 1
                    self._var2color[v] = i
                else:
                    i += 1

            raise ValueError("There must exist a colour that has not been assigned so far")

    def _release_colour(self, v: var_id_T, available: List[bool]):
        self._used_colors -= 1
        available[self._var2color[v]] = True
        self._assigned_colours.remove(v)

    def _assign_color(self, block_id: block_id_T, available: List[bool]) -> None:
        """
        We need to assign colours to each different block, following the cfg order.
        """
        block = self._block_list.get_block(block_id)

        # Then, we traverse the instructions
        new_greedy_ids = []
        for instruction_id in block.greedy_ids:
            # SET instructions can convert into POP or
            if instruction_id.startswith("SET"):
                variable_id = instruction_id[4: -1]

                # If it has been already assigned, then we replace with a POP instruction
                if variable_id in self._assigned_colours:
                    new_greedy_ids.append("POP")
                else:
                    self._pick_colour(variable_id, available)

            # We must release the colour for GET instructions
            # if this is the last occurrence in the corresponding
            # branch of the tree
            elif instruction_id.startswith("GET"):

                variable_id = instruction_id[4:-1]

            else:
                new_greedy_ids.append(instruction_id)

        block.greedy_ids = new_greedy_ids

        # The variables in ordered_program_points indicate which variables
        # have the last use at the current block, and can be released.
        for variable in self._ordered_program_points.get(block_id, []):
            self._release_colour(variable, available)

        for successor in self._dominance_tree.successors(block_id):
            self._assign_color(successor, available.copy())

    def tree_scan_with_last_uses(self) -> None:
        """
        Adapted from Algorithm 22.1: Tree scan in page 309. Given the block list,
        and the list of program points, registers are assigned based on colours
        """
        # Initial call with the start block and an empty list of available blocks
        self._assign_color(self._block_list.start_block, [])
