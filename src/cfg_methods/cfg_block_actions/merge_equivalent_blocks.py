"""
Merges two equivalent blocks of the same block list (see cfg_methods/equivalent_blocks_merging.py):
same instructions and successors, with a one-to-one correspondence between their variables.
The duplicate block is removed and its predecessors jump to the representative, introducing
phi-functions for the input values that differ between both blocks.
"""
from typing import List, Dict, Optional, Callable
from cfg_methods.cfg_block_actions.actions_interface import BlockAction
from cfg_methods.cfg_block_actions.utils import modify_successors, remove_comes_from
from global_params.types import var_id_T
from parser.cfg_block_list import CFGBlockList
from parser.cfg_block import CFGBlock
from parser.cfg_instruction import CFGInstruction


def phi_entries(block: CFGBlock) -> List[str]:
    """
    Predecessors of the block in the order used by the arguments of its phi-functions. Blocks with
    no phi-functions might have no entries, so we use the "comes from" list instead
    """
    return list(block.entries) if len(block.phi_instructions()) > 0 else list(block.get_comes_from())


def values_per_entry(block: CFGBlock, input_var: var_id_T) -> List[var_id_T]:
    """
    Values that input_var takes along each of the incoming edges of the block (in phi_entries order):
    the arguments of the phi-function if input_var is defined by one in the block, or input_var itself
    otherwise
    """
    for phi_instr in block.phi_instructions():
        if phi_instr.get_out_args()[0] == input_var:
            return list(phi_instr.get_in_args())
    return [input_var] * len(phi_entries(block))


class MergeEquivalentBlocks(BlockAction):
    """
    Merges the duplicate block into the representative one. Both blocks must have the same canonical
    signature: the input variables (used but not defined by non-phi instructions, including phi outputs)
    at the same position correspond to each other, and so do local definitions. The successors must be
    the same and the blocks cannot share predecessors. As both blocks are predecessors of every
    successor, local definitions only leave the blocks through the phi arguments of the successors,
    so the transformation only affects the representative, the duplicate predecessors and the
    phi-functions of the successors.
    """

    def __init__(self, representative: CFGBlock, representative_inputs: List[var_id_T],
                 duplicate: CFGBlock, duplicate_inputs: List[var_id_T], cfg_blocklist: CFGBlockList,
                 fresh_variable: Callable[[var_id_T], var_id_T]):
        self._representative: CFGBlock = representative
        self._representative_inputs: List[var_id_T] = representative_inputs
        self._duplicate: Optional[CFGBlock] = duplicate
        self._duplicate_inputs: List[var_id_T] = duplicate_inputs
        self._cfg_blocklist: CFGBlockList = cfg_blocklist
        self._fresh_variable: Callable[[var_id_T], var_id_T] = fresh_variable

        self._representative_id = representative.block_id
        self._duplicate_id = duplicate.block_id

    def perform_action(self):
        # Computed before modifying anything, as the phi-functions of the representative are extended
        representative_entries = phi_entries(self._representative)
        duplicate_entries = phi_entries(self._duplicate)
        phi_outputs_representative = {phi_instr.get_out_args()[0]: phi_instr
                                      for phi_instr in self._representative.phi_instructions()}

        # Renaming of the input variables of the representative that become phi-functions
        renaming_dict: Dict[var_id_T, var_id_T] = dict()
        new_phi_instrs = []
        for representative_var, duplicate_var in zip(self._representative_inputs, self._duplicate_inputs):
            is_phi_representative = representative_var in phi_outputs_representative
            duplicate_values = values_per_entry(self._duplicate, duplicate_var)

            if is_phi_representative:
                # Extend the existing phi-function with the values from the new predecessors
                phi_instr = phi_outputs_representative[representative_var]
                phi_instr.set_in_args(phi_instr.get_in_args() + duplicate_values)

            elif representative_var != duplicate_var or duplicate_values != [duplicate_var] * len(duplicate_entries):
                # The value is defined outside the representative, so it can only be renamed inside it
                phi_var = self._fresh_variable(representative_var)
                renaming_dict[representative_var] = phi_var
                representative_values = [representative_var] * len(representative_entries)
                new_phi_instrs.append(CFGInstruction("PhiFunction", representative_values + duplicate_values,
                                                     [phi_var]))

            # Otherwise, both blocks use the same variable, defined outside them

        self._rename_inputs_representative(renaming_dict)

        # Phi-functions must come first
        for i, phi_instr in enumerate(new_phi_instrs):
            self._representative.insert_instruction(i, phi_instr)

        self._representative.entries = representative_entries + duplicate_entries
        self._representative.set_comes_from(self._representative.get_comes_from() +
                                            self._duplicate.get_comes_from())

        # The predecessors of the duplicate now reach the representative
        for pred_block_id in self._duplicate.get_comes_from():
            modify_successors(pred_block_id, self._duplicate_id, self._representative_id, self._cfg_blocklist)

        # The successors are no longer reached from the duplicate
        for successor_id in self._duplicate.successors:
            remove_comes_from(successor_id, self._duplicate_id, self._cfg_blocklist)

        self._cfg_blocklist.remove_block(self._duplicate_id)
        del self._duplicate

    def _rename_inputs_representative(self, renaming_dict: Dict[var_id_T, var_id_T]) -> None:
        """
        Renames the uses of the input variables in the non-phi instructions, the condition and the
        phi arguments of the successors along the edges from the representative
        """
        if len(renaming_dict) == 0:
            return

        for instr in self._representative.instructions_without_phi_functions():
            instr.set_in_args([renaming_dict.get(in_arg, in_arg) for in_arg in instr.get_in_args()])

        condition = self._representative.get_condition()
        if condition is not None:
            self._representative.set_condition(renaming_dict.get(condition, condition))

        for successor_id in self._representative.successors:
            successor = self._cfg_blocklist.get_block(successor_id)
            entry_idx = successor.entries.index(self._representative_id) \
                if len(successor.phi_instructions()) > 0 else None
            for phi_instr in successor.phi_instructions():
                phi_args = phi_instr.get_in_args()
                phi_args[entry_idx] = renaming_dict.get(phi_args[entry_idx], phi_args[entry_idx])

    def __str__(self):
        return f"MergeEquivalentBlocks {self._duplicate_id} into {self._representative_id}"
