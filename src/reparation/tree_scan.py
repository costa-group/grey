"""
Module that implements an alternative version the Tree Scan algorithm from
"SSA-based Compiler Design" (Algorithm 22.1, page 309). The key difference is that we assume
an unbounded number of registers to colour, as the EVM memory can
grow indefinitely (although dangerously in cost...).

The values stored in memory must have a single definition (see reparation.memory_values) and their
liveness is computed beforehand (see reparation.memory_liveness), following the multiplexing mode for
phi-functions (Definition 21.1): phi defs are live-in of their block and their arguments are live-out
of the predecessors. Hence, the colours are released:
  - At the entry of a block, for the values that are not live-in.
  - After the last access within a block, for the values that are not live-out.
The copies for the phi defs are placed at the end of the predecessors, before the jump, so they are
executed in all the edges leaving the predecessor. Thus, a phi def cannot share the colour of any value
live in another successor of its predecessors (lost-copy problem, Sect. 21.1).
"""
from typing import List, Tuple, Dict, Set
from global_params.types import block_id_T, constant_T, var_id_T, instr_id_T
from parser.cfg_block_list import CFGBlockList
from reparation.colour_assignment import ColourAssignment, owners_T
from reparation.phi_webs import PhiWebs
from reparation.utils import extract_value_from_pseudo_instr, extract_dup_pos_from_dup_vset


def phi_copy_interferences(block_list: CFGBlockList) -> Dict[var_id_T, Set[var_id_T]]:
    """
    For each phi def handled in memory, the values that are live when its slot is written by the copy at
    the end of a predecessor, apart from the argument copied (which can share its slot). The relation is
    symmetric, so it can be queried when colouring any of the two values
    """
    memory_values = set()
    for block in block_list.blocks.values():
        memory_values.update(block.greedy_info.phi_defs_to_solve)
        for instr_id in block.greedy_info.greedy_ids:
            if instr_id.startswith("VSET") or instr_id.startswith("DUP-VSET"):
                memory_values.add(extract_value_from_pseudo_instr(instr_id))

    interferences: Dict[var_id_T, Set[var_id_T]] = {}
    for block_id, block in block_list.blocks.items():
        # Values live after the parallel copy at the end of the block (not only used by the copies)
        live_after_copies = set()
        for successor_id in block.successors:
            successor = block_list.get_block(successor_id)
            live_after_copies |= successor.greedy_info.memory_live_in - successor.greedy_info.phi_defs_to_solve

        # All the phi defs written at the end of the block (both from memory and through DUP)
        for successor_id in block.successors:
            successor = block_list.get_block(successor_id)
            if not successor.entries:
                continue
            entry_idx = successor.entries.index(block_id)
            for phi_instr in successor.phi_instructions():
                phi_def = phi_instr.out_args[0]
                if phi_def not in successor.greedy_info.phi_defs_to_solve:
                    continue
                argument = phi_instr.in_args[entry_idx]
                for value in live_after_copies:
                    if value != argument and value != phi_def:
                        interferences.setdefault(phi_def, set()).add(value)
                        interferences.setdefault(value, set()).add(phi_def)
    return interferences


class TreeScan:
    """
    Class to represents the colouring of the graph using a tree scan pass
    """

    def __init__(self, block_list: CFGBlockList,
                 phi_webs: PhiWebs, num_colors_max: int,
                 max_constant: constant_T):

        # Parameters that are passed to colour the graph
        self._block_list = block_list

        # To identify the classes
        self._phi_webs = phi_webs

        # We aim to coalesce all
        self._phi_class2colors = {phi_class: [] for phi_class in phi_webs.classes_with_elements}

        # Number of possible colors
        self._num_colors_max = num_colors_max

        # From which constant the assignments can be performed
        self._max_constant = max_constant

        # Extra interferences due to the placement of the phi copies
        self._copy_interferences = phi_copy_interferences(block_list)

    def _assign_color(self, block_name: block_id_T, color_assignment: ColourAssignment, owners: owners_T):
        """
        Colours the values defined in the block and returns the owners of the colours at the end of it
        """
        block = self._block_list.get_block(block_name)
        greedy_info = block.greedy_info

        # Values that are not live-in are dead in the whole dominator subtree of the block
        color_assignment.release_dead(owners, greedy_info.memory_live_in)

        # The phi defs handled in memory are defined at the entry of the block
        for phi_instr in block.phi_instructions():
            phi_def = phi_instr.out_args[0]
            if phi_def in greedy_info.phi_defs_to_solve:
                self._biased_pick_color(phi_def, color_assignment, owners)

        for i, instr_id in enumerate(greedy_info.greedy_ids):
            # Both VSET and DUP-VSET define a new value (a single time)
            if instr_id.startswith("VSET") or instr_id.startswith("DUP-VSET"):
                self._biased_pick_color(extract_value_from_pseudo_instr(instr_id), color_assignment, owners)

            # Release the colour after the last access to a value that is not live-out
            if i in greedy_info.last_use:
                color_assignment.release_colour(extract_value_from_pseudo_instr(instr_id), owners)

        return owners

    def _biased_pick_color(self, var: var_id_T, color_assignment: ColourAssignment,
                           owners: owners_T):
        """
        Picks a colour for var. If var belongs to a phi web, it reuses the most recent colour
        of that web that is still available, so that the phi-related values share the same
        memory slot and no copies are needed. Otherwise, it picks the first available colour.
        Colours of values that interfere due to the phi copies are never picked
        """
        forbidden = {color_assignment.color(value) for value in self._copy_interferences.get(var, ())
                     if color_assignment.is_coloured(value)}

        # Only try to bias the colouring for variables with conflicts
        if self._phi_webs.has_element(var):
            phi_class = self._phi_webs.find_set(var)
            # Exactly one colour must be picked
            for biased_color in reversed(self._phi_class2colors[phi_class]):
                if color_assignment.is_available(biased_color, owners) and biased_color not in forbidden:
                    color_assignment.pick_specific_colour(var, owners, biased_color)
                    return

            # Otherwise, just pick a colour
            # TODO: heuristics for picking a color
            new_color = color_assignment.pick_available_colour(var, owners, forbidden)
            self._phi_class2colors[phi_class].append(new_color)
        else:
            color_assignment.pick_available_colour(var, owners, forbidden)

    def _tree_scan_with_last_uses(self) -> ColourAssignment:
        """
        Adapted from Algorithm 22.1: Tree scan in page 309. Given the block list,
        and the list of program points, registers are assigned based on colours.
        The dominator tree is traversed in preorder (iteratively, to avoid the recursion
        limit), passing a copy of the owners of the colours to each child
        """
        color_assignment = ColourAssignment()
        pending = [(self._block_list.start_block, [None] * self._num_colors_max)]
        while pending:
            block_name, owners = pending.pop()
            owners_at_exit = self._assign_color(block_name, color_assignment, owners)
            for successor in sorted(self._block_list.dominant_tree.successors(block_name), reverse=True):
                pending.append((successor, owners_at_exit.copy()))
        return color_assignment

    # Last step: replacing the corresponding values by colour
    # and emitting the copy assignments. Copy assignments are
    # easier for stack-based machine because we can just load
    # in the stack and store them adequately

    # HACK: assign to PUSH2 0x80 to the color that is repeated the most
    # (both by accessing VGET + VGET-VSET + VSET).
    # For the other colours, we don't care
    def _emit_valid_bytecode(self, color_assignment: ColourAssignment, max_constant: str):
        """
        Given the final colour assignment, we perform the SSA destruction
        by generating the copy assignments to solve phi-interferences.
        """
        color_to_constant = self._assign_colours_to_constants(self._num_colors_max, max_constant)

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
                    new_greedy_ids.extend(self._emit_copies(copies_to_manage_regs,
                                                            copies_to_manage_dup,
                                                            color_to_constant))

            # FINALLY we assign the greedy ids corrected to the corresponding field
            block.greedy_ids = new_greedy_ids
        return color_to_constant

    def _emit_vget(self, constant: constant_T) -> List[instr_id_T]:
        return [f"PUSH {constant}", "MLOAD"]

    def _emit_vset(self, constant: constant_T) -> List[instr_id_T]:
        return [f"PUSH {constant}", "MSTORE"]

    def _emit_dup_vset(self, constant: constant_T, dup_pos: int) -> List[instr_id_T]:
        return [f"DUP{dup_pos + 1}"] + self._emit_vset(constant)

    def _assign_colours_to_constants(self, num_colors: int, max_constant: str) -> List[constant_T]:
        # TODO: implement HACK2 (not very difficult)
        return [hex(int(max_constant, 16) + 32 * i)[2:] for i in range(num_colors)]

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
            # pos_to_dup is the (0-based) position of the value at the end of the block, as in DUP-VSET
            # (the stores of the previous copies leave the stack as it was)
            ids_for_copies.extend(self._emit_dup_vset(constant_dst, pos_to_dup))

        return ids_for_copies

    def executable_from_code(self):
        color_assignment = self._tree_scan_with_last_uses()
        color2constant = self._emit_valid_bytecode(color_assignment, self._max_constant)
        return color_assignment, color_assignment.next_constant(color2constant)
