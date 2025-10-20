"""
Module that implements an alternative version the Tree Scan algorithm from
"SSA-based Compiler Design" (Page 309). The key difference is that we assume
an unbounded number of registers to colour, as the EVM memory can
grow indefinitely (although dangerously in cost...). Moreover, the liveness sets
are determined according to the last point in which a variable could be accessed
"""
from typing import List
from global_params.types import block_id_T, constant_T, var_id_T
from parser.cfg_block_list import CFGBlockList
from reparation.colour_assignment import ColourAssignment
from reparation.phi_webs import PhiWebs
from reparation.utils import extract_value_from_pseudo_instr, extract_dup_pos_from_dup_vset


class TreenScan:
    """
    Class to represents the colouring of the graph using a tree scan pass
    """

    def __init__(self, block_list: CFGBlockList,
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

        # First, we process the phi instructions that we must handle
        for phi_instr in block.phi_instructions():

            if phi_instr.out_args[0] in greedy_info.phi_defs_to_solve:
                # First, we must check the arguments

                self._biased_pick_color(var, color_assignment, available)

        for i, instr_id in enumerate(greedy_info.greedy_ids):
            # First process the values in
            if instr_id.startswith("VGET"):
                # Just release the colour if it is the last use
                if i in greedy_info.last_use:
                    var = extract_value_from_pseudo_instr(instr_id)
                    color_assignment.release_colour(var, available)

            # Both VSET and DUP-VSET are handled accordingly
            elif "VSET" in instr_id:
                var = extract_value_from_pseudo_instr(instr_id)
                self._biased_pick_color(var, color_assignment, available)

        # We invoke the call to the children
        for successor in self._block_list.dominant_tree.successors(block_name):
            self._assign_color(successor, color_assignment, available.copy())

    def _biased_pick_color(self, var: var_id_T, color_assignment: ColourAssignment,
                           available: List[bool]):
        """
        Picks the class colour (if any) to favour the encoding
        """
        phi_class = self._phi_webs.find_set(var)
        # We try to bias the assignment
        for biased_color in reversed(self._phi_class2colors[phi_class]):
            if available[biased_color]:
                color_assignment.pick_specific_colour(var, available, biased_color)

        # Otherwise, just pick a colour
        # TODO: heuristics for picking a color
        new_color = color_assignment.pick_available_colour(var, available)
        self._phi_class2colors[phi_class].append(new_color)

    def _tree_scan_with_last_uses(self) -> ColourAssignment:
        """
        Adapted from Algorithm 22.1: Tree scan in page 309. Given the block list,
        and the list of program points, registers are assigned based on colours
        """
        color_assignment = ColourAssignment()
        # Initial call with the start block and an empty list of available blocks
        self._assign_color(self._block_list.start_block, color_assignment, [])
        return color_assignment

    # Last step: replacing the corresponding values by colour
    # and emitting the copy assignments. Copy assignments are
    # easier for stack-based machine because we can just load
    # in the stack and store them adequately

    # HACK1: we know which phi-functions are "modelled"
    # in our problem: the ones that appear in the phi-webs.
    # Hence, we will use this data structure

    # HACK2: assign to PUSH2 0x80 to the color that is repeated the most
    # (both by accessing VGET + VGET-VSET + VSET).
    # For the other colours, we don't care
    def _emit_valid_bytecode(self, color_assignment: ColourAssignment):
        """
        Given the final colour assignment, we perform the SSA destruction
        by generating the copy assignments to solve phi-interferences.
        """
        color_to_constant = self._assign_colours_to_constants(color_assignment)

        # Here we don't care about the order in which the block lists are traversed
        for block_name, block in self._block_list.blocks.items():
            greedy_info = block.greedy_info

            new_greedy_ids = []
            for i, instr_id in enumerate(greedy_info.greedy_ids):
                if instr_id.startswith("VGET"):
                    var = extract_value_from_pseudo_instr(instr_id)
                    new_greedy_ids.extend([f"PUSH {color_to_constant[color_assignment.color(var)]}", "MLOAD"])

                # Both VSET and DUP-VSET are handled accordingly
                elif instr_id.startswith("VSET"):
                    var = extract_value_from_pseudo_instr(instr_id)
                    new_greedy_ids.extend([f"PUSH {color_to_constant[color_assignment.color(var)]}", "MSTORE"])

                elif instr_id.startswith("DUP-VSET"):
                    var = extract_value_from_pseudo_instr(instr_id)
                    dup_pos = extract_dup_pos_from_dup_vset(instr_id)
                    new_greedy_ids.extend([f"DUP{dup_pos}", f"PUSH {color_to_constant[color_assignment.color(var)]}",
                                           "MSTORE"])
                else:
                    # We respect the greedy ids
                    new_greedy_ids.append(instr_id)

            # If there are some virtual copies that need to be managed,
            # it means we have to emit copies for phi-functions
            if len(greedy_info.virtual_copies) > 0:
                copies_to_manage = []
                for successor_name in block.successors:
                    successor_block = self._block_list.get_block(successor_name)

                    # This means that there is a phi-function there
                    if len(successor_block.entries) > 0:
                        phi_instrs = successor_block.phi_instructions()
                        successor_greedy_info = successor_block.greedy_info
                        assert len(phi_instrs) > 0, "There must be at least one phi instruction"

                        # We only care about the phi instruction that define
                        # a value which appears in our (phi values to fix)
                        for phi in phi_instrs:
                            phi_def = phi.out_args[0]
                            if phi_def in successor_greedy_info.phi_defs_to_solve:
                                color_phi = self._

                if copies_to_manage:
                    new_greedy_ids.extend(self._emit_copies(block_name, ))

    def _assign_colours_to_constants(self, color_assignment: ColourAssignment) -> List[constant_T]:
        # TODO: implement HACK2 (not very difficult)
        return [hex(128 + 32*i) for i in range(color_assignment.num_colors)]

    def executable_from_code(self):
        pass
