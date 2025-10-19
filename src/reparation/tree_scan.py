"""
Module that implements an alternative version the Tree Scan algorithm from
"SSA-based Compiler Design" (Page 309). The key difference is that we assume
an unbounded number of registers to colour, as the EVM memory can
grow indefinitely (although dangerously in cost...). Moreover, the liveness sets
are determined according to the last point in which a variable could be accessed
"""
import networkx as nx
from collections import defaultdict
from global_params.types import var_id_T, block_id_T, element_definition_T, instr_id_T
from typing import List, Dict, Tuple, Set, Optional
from parser.cfg_block import CFGBlock
from parser.cfg_block_list import CFGBlockList
from reparation.colour_assignment import ColourAssignment
from reparation.phi_webs import PhiWebs
from reparation.utils import extract_value_from_pseudo_instr


class TreenScan:
    """
    Class to represents the colouring of the graph using a tree scan pass
    """

    def __init__(self, block_list: CFGBlockList,
                 colour_assignment: ColourAssignment,
                 phi_webs: PhiWebs):

        # Parameters that are passed to colour the graph
        self._block_list = block_list

        # To identify the classes
        self._phi_webs = phi_webs

        # We aim to coalesce all
        self._phi_class2colors = [[]] * phi_webs.num_sets

    def _assign_color(self, block_name: block_id_T, color_assignment: ColourAssignment, available: List[bool]):
        block = self._block_list.get_block(block_name)
        greedy_info = block.greedy_info

        for i, instr_id in enumerate(greedy_info.greedy_ids):
            # First process the values in
            if instr_id == "VGET":
                # Just release the colour if it is the last use
                if i in greedy_info.last_use:
                    var = extract_value_from_pseudo_instr(instr_id)
                    color_assignment.release_colour(var, available)

            # Both VSET and DUP-VSET are handled accordingly
            elif "VSET" in instr_id:
                var = extract_value_from_pseudo_instr(instr_id)

                phi_class = self._phi_webs.find_set(var)
                # We try to bias the assignment
                for biased_color in reversed(self._phi_class2colors[phi_class]):
                    if available[biased_color]:
                        color_assignment.pick_specific_colour(var, available, biased_color)

                # Otherwise, just pick a colour
                # TODO: heuristics for picking a color
                new_color = color_assignment.pick_available_colour(var, available)
                self._phi_class2colors[phi_class].append(new_color)

        # We invoke the call to the children
        for successor in self._block_list.dominant_tree.successors(block_name):
            self._assign_color(successor, color_assignment, available.copy())

    def tree_scan_with_last_uses(self) -> ColourAssignment:
        """
        Adapted from Algorithm 22.1: Tree scan in page 309. Given the block list,
        and the list of program points, registers are assigned based on colours
        """
        color_assignment = ColourAssignment()
        # Initial call with the start block and an empty list of available blocks
        self._assign_color(self._block_list.start_block, color_assignment, [])
        return color_assignment
