from typing import Optional, Tuple
from cfg_methods.cfg_block_actions.actions_interface import BlockAction
from cfg_methods.cfg_block_actions.utils import modify_comes_from, modify_successors
from parser.cfg_block_list import CFGBlockList
from parser.cfg_block import CFGBlock


def split_blocks_ids(current_node: str) -> Tuple[str, str]:
    """
    Given a node, generates a new name for the resulting split
    """
    return current_node + "_s0", current_node + "_s1"


class SplitBlock(BlockAction):
    """
    Splits a block at a given instruction (including it in the first half).
    It needs the corresponding blocklist to update the fields correspondingly
    """

    def __init__(self, instr_idx: int, cfg_block: CFGBlock, cfg_blocklist: CFGBlockList):
        # We add one to the index so that it points to the initial instruction of the second half
        self._instr_idx: int = instr_idx + 1
        self._cfg_block: Optional[CFGBlock] = cfg_block
        self._cfg_block_list: CFGBlockList = cfg_blocklist
        self._initial_id = self._cfg_block.block_id
        self._first_half: Optional[CFGBlock] = None
        self._second_half: Optional[CFGBlock] = None

    def perform_action(self):
        is_start_block = self._cfg_block.block_id == self._cfg_block_list.start_block
        first_half_id, second_half_id = split_blocks_ids(self._initial_id)

        # We reuse the block name, so we don't need to modify the previous blocks
        first_half = CFGBlock(first_half_id, self._cfg_block.get_instructions()[:self._instr_idx], "sub_block",
                              self._cfg_block.assignment_dict)

        # We preserve the previous type if exists
        first_half.previous_type = first_half.previous_type if first_half.previous_type is not None else first_half.get_jump_type()
        self._first_half = first_half

        # Then we generate the second half
        second_half = CFGBlock(second_half_id, self._cfg_block.get_instructions()[self._instr_idx:],
                               self._cfg_block.get_jump_type(), self._cfg_block.assignment_dict)
        self._second_half = second_half

        # We update the jump information of both halves
        self._update_first_half()
        self._update_second_half()

        # Remove the initial block from the list of blocks
        self._cfg_block_list.remove_block(self._initial_id)

        # Include the newly generated blocks in the list
        self._cfg_block_list.add_block(first_half, is_start_block)
        self._cfg_block_list.add_block(second_half)

        # is_correct, reason = validate_block_list_comes_from(self._cfg_block_list)

        # We remove the old block (so no reference points to it)
        del self._cfg_block

    def _update_first_half(self):
        # We need to update the corresponding information from both the first and second half
        self._first_half.entries = self._cfg_block.entries
        self._first_half.set_comes_from(self._cfg_block.get_comes_from())
        self._first_half.set_falls_to(self._second_half.block_id)
        self._first_half.set_jump_to(None)

        # Finally, we update the information from the blocks that jumped (or fell) to the first one
        for pred_block_id in self._cfg_block.get_comes_from():
            modify_successors(pred_block_id, self._initial_id, self._first_half.block_id, self._cfg_block_list)

    def _update_second_half(self):
        # We need to update the corresponding information
        self._second_half.set_comes_from([self._first_half.block_id])
        self._second_half.set_falls_to(self._cfg_block.get_falls_to())
        self._second_half.set_jump_to(self._cfg_block.get_jump_to())
        self._second_half.set_condition(self._cfg_block.get_condition())

        # Finally, we update the comes from information from the blocks that are reached afterwards
        initial_jumps_to = self._cfg_block.get_jump_to()
        initial_falls_to = self._cfg_block.get_falls_to()

        if initial_jumps_to is not None:
            modify_comes_from(initial_jumps_to, self._initial_id, self._second_half.block_id, self._cfg_block_list)
        if initial_falls_to is not None:
            modify_comes_from(initial_falls_to, self._initial_id, self._second_half.block_id, self._cfg_block_list)

    @property
    def first_half(self) -> Optional[CFGBlock]:
        return self._first_half

    @property
    def second_half(self) -> Optional[CFGBlock]:
        return self._second_half

    def __str__(self):
        return f"SplitBlock {self._initial_id} at instruction with index {self._instr_idx}"
