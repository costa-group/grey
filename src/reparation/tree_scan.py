"""
Module that implements an alternative version the Tree Scan algorithm from
"SSA-based Compiler Design" (Page 309). The key difference is that we assume
an unbounded number of registers to colour, as the EVM memory can
grow indefinitely (although dangerously in cost...). Moreover, the liveness sets
are determined according to the last point in which a variable could be accessed
"""
from typing import List, Tuple, Dict
from global_params.types import block_id_T, constant_T, var_id_T, instr_id_T
from parser.cfg_block_list import CFGBlockList
from reparation.colour_assignment import ColourAssignment
from reparation.phi_webs import PhiWebs
from reparation.utils import extract_value_from_pseudo_instr, extract_dup_pos_from_dup_vset


class TreeScan:
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
            out_arg = phi_instr.out_args[0]
            if out_arg in greedy_info.phi_defs_to_solve:
                # First, we must check the arguments
                for in_arg in phi_instr.in_args:

                    # Case -1: it corresponds to a phi argument
                    if (-1, in_arg) in greedy_info.last_use:
                        color_assignment.release_colour(in_arg, available)

                # Then we assign the generated value
                self._biased_pick_color(phi_instr.out_args[0], color_assignment, available)

        # Then, we update the greedy ids
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

        # Finally, we check the values that are passed to phi-functions
        for value in greedy_info.virtual_copies:
            # Case -2: PhiDefs
            if (-2, value) in greedy_info.last_use:
                color_assignment.release_colour(value, available)

        # We invoke the call to the children
        for successor in self._block_list.dominant_tree.successors(block_name):
            self._assign_color(successor, color_assignment, available.copy())

    def _biased_pick_color(self, var: var_id_T, color_assignment: ColourAssignment,
                           available: List[bool]):
        """
        Picks the class colour (if any) to favour the encoding
        """
        # Only try to bias the colouring for variables with conflicts
        if self._phi_webs.has_element(var):
            phi_class = self._phi_webs.find_set(var)
            # We try to bias the assignment
            for biased_color in reversed(self._phi_class2colors[phi_class]):
                if available[biased_color]:
                    color_assignment.pick_specific_colour(var, available, biased_color)

            # Otherwise, just pick a colour
            # TODO: heuristics for picking a color
            new_color = color_assignment.pick_available_colour(var, available)
            self._phi_class2colors[phi_class].append(new_color)
        else:
            color_assignment.pick_available_colour(var, available)

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

    # HACK: assign to PUSH2 0x80 to the color that is repeated the most
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
                    constant = color_to_constant[color_assignment.color(var)]
                    new_greedy_ids.extend(self._emit_vget(constant))

                # Both VSET and DUP-VSET are handled accordingly
                elif instr_id.startswith("VSET"):
                    var = extract_value_from_pseudo_instr(instr_id)
                    constant = color_to_constant[color_assignment.color(var)]
                    new_greedy_ids.extend(self._emit_vset(constant))

                elif instr_id.startswith("DUP-VSET"):
                    var = extract_value_from_pseudo_instr(instr_id)
                    dup_pos = extract_dup_pos_from_dup_vset(instr_id)
                    constant = color_to_constant[color_assignment.color(var)]

                    new_greedy_ids.extend(self._emit_dup_vset(constant, dup_pos))
                else:
                    # We respect the greedy ids
                    new_greedy_ids.append(instr_id)

            # If there are some virtual copies that need to be managed,
            # it means we have to emit copies for phi-functions
            if len(greedy_info.virtual_copies) > 0:
                # We separate values that must be loaded from registers
                # and those that are duplicated
                copies_to_manage_regs = dict()
                copies_to_manage_dup = dict()

                for successor_name in block.successors:
                    successor_block = self._block_list.get_block(successor_name)

                    # This means that there is a phi-function there
                    if len(successor_block.entries) > 0:
                        phi_instrs = successor_block.phi_instructions()
                        successor_greedy_info = successor_block.greedy_info
                        assert len(phi_instrs) > 0, "There must be at least one phi instruction"
                        entry_idx = successor_block.entries.index(block_name)
                        # We only care about the phi instruction that define
                        # a value which appears in our (phi values to fix)
                        for phi_instr in phi_instrs:
                            phi_def = phi_instr.out_args[0]
                            if phi_def in successor_greedy_info.phi_defs_to_solve:
                                color_phi = color_assignment.color(phi_def)
                                phi_arg = phi_instr.in_args[entry_idx]

                                # The phi arg might not have a color
                                # is we could just duplicate it
                                if color_assignment.is_coloured(phi_arg):
                                    color_phi_arg = color_assignment.color(phi_arg)

                                    # They have different colours, so we need to emit a copy.
                                    if color_phi_arg != color_phi:
                                        copies_to_manage_regs[phi_arg] = (color_phi, color_phi_arg)

                                # Otherwise, we just need to duplicate it
                                # and put it in their position. We store the position to dup
                                else:
                                    dup_pos, _, is_last = greedy_info.reachable[phi_arg]
                                    assert is_last, f"A variable that is duplicated must be reachable at that point: {phi_arg}"
                                    copies_to_manage_dup[phi_arg] = (color_phi, dup_pos)

                if copies_to_manage_dup or copies_to_manage_regs:
                    new_greedy_ids.extend(self._emit_copies(block_name, copies_to_manage_regs,
                                                            copies_to_manage_dup))

            # FINALLY we assign the greedy ids corrected to the corresponding field
            block.greedy_ids = greedy_info

    def _emit_vget(self, constant: constant_T) -> List[instr_id_T]:
        return [f"PUSH {constant}", "MLOAD"]

    def _emit_vset(self, constant: constant_T) -> List[instr_id_T]:
        return [f"PUSH {constant}", "MSTORE"]

    def _emit_dup_vset(self, constant: constant_T, dup_pos: int) -> List[instr_id_T]:
        return [f"DUP{dup_pos + 1}"] + self._emit_vset(constant)

    def _assign_colours_to_constants(self, color_assignment: ColourAssignment) -> List[constant_T]:
        # TODO: implement HACK2 (not very difficult)
        return [hex(128 + 32*i) for i in range(color_assignment.num_colors)]

    def _emit_copies(self, copies_to_manage_regs: Dict[var_id_T, Tuple[int, int]],
                     copies_to_manage_dup: Dict[var_id_T, Tuple[int, int]],
                     color2constant: List[constant_T]) -> List[instr_id_T]:
        """
        Emites instructions that ensure every value in a
        """
        ids_for_copies = []

        colors2store = []
        # First we solve the values that have values that
        # must be loaded from registers
        for variable, (color_dst, color_orig) in copies_to_manage_regs.items():
            constant = color2constant[color_orig]
            ids_for_copies.extend(self._emit_vget(constant))
            colors2store.insert(0, color_dst)

        # Now, we traverse them as a stack to
        # place in their corresponding position
        for color2store in colors2store:
            constant_dst = color2constant[color2store]
            ids_for_copies.extend(self._emit_vset(constant_dst))

        # Finally, we solve the values that can be dupped as DUP-VSET
        for variable, (color_dst, pos_to_dup) in copies_to_manage_dup.items():
            # Finally, we solve the remaining values one by one, so that
            # they can always be dupped and assigned to the corresponding register
            constant_dst = color2constant[color_dst]
            ids_for_copies.extend(self._emit_dup_vset(constant_dst, pos_to_dup + 1))

        return ids_for_copies

    def executable_from_code(self):
        color_assignment = self._tree_scan_with_last_uses()
        self._emit_valid_bytecode(color_assignment)
