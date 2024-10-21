from typing import Optional
from parser.cfg_block_actions.actions_interface import BlockAction
from parser.cfg_block_list import CFGBlockList
from parser.cfg_block import CFGBlock
from parser.cfg_instruction import CFGInstruction
from global_params.types import block_id_T


def new_node_name(current_node: str) -> str:
    """
    Given a node, generates a new name for the resulting split
    """
    split_name = current_node.split("_")
    if len(split_name) > 1:
        split_name[1] = str(int(split_name[1]) + 1)
        return '_'.join(split_name)
    else:
        return current_node + "_1"


class SplitBlock(BlockAction):
    """
    Splits a block at a given instruction (including it in the first half).
    It needs the corresponding blocklist to update the fields correspondingly
    """

    def __init__(self, cfg_instruction: CFGInstruction, cfg_block: CFGBlock, cfg_blocklist: CFGBlockList):
        self._cfg_instruction: CFGInstruction = cfg_instruction
        self._cfg_block: Optional[CFGBlock] = cfg_block
        self._cfg_block_list: CFGBlockList = cfg_blocklist
        self._initial_id = self._cfg_block.block_id
        self._first_half: Optional[CFGBlock] = None
        self._second_half: Optional[CFGBlock] = None

    def perform_action(self):
        # First we find the index of the instruction. It is included as part of the first split block
        instr_idx = self._cfg_block.get_instructions().index(self._cfg_instruction) + 1

        #
        first_half_id = new_node_name(self._initial_id)
        second_half_id = new_node_name(first_half_id)

        # We reuse the block name, so we don't need to modify the previous blocks
        first_half = CFGBlock(first_half_id, self._cfg_block.get_instructions()[:instr_idx], "sub_block",
                              self._cfg_block.assignment_dict)
        self._first_half = first_half

        # Then we generate the second half
        second_half = CFGBlock(second_half_id, self._cfg_block.get_instructions()[instr_idx:],
                               self._cfg_block.get_jump_type(), self._cfg_block.assignment_dict)
        self._second_half = second_half

        # We update the jump information of both halves
        self._update_first_half()
        self._update_second_half()

        # Remove the initial block from the list of blocks
        del self._cfg_block_list.blocks[self._initial_id]

        # Include the newly generated blocks in the list
        self._cfg_block_list.add_block(first_half)
        self._cfg_block_list.add_block(second_half)

        # We remove the old block (so no reference points to it)
        del self._cfg_block

    def _update_first_half(self):
        # We need to update the corresponding information from both the first and second half
        self._first_half.set_comes_from(self._cfg_block.get_comes_from())
        self._first_half.set_falls_to(self._second_half.block_id)
        self._first_half.set_jump_to(None)
        # We need to force the input arguments of the instruction we have use to split
        self._first_half.final_stack_elements = self._cfg_instruction.get_in_args()

        # Finally, we update the information from the blocks that jumped (or fell) to the first one
        for pred_block_id in self._cfg_block.get_comes_from():
            pred_block = self._cfg_block_list.blocks[pred_block_id]
            if pred_block.get_jump_to():
                pred_block.set_jump_to(self._first_half.block_id)
            else:
                falls_to = pred_block.get_falls_to()
                assert falls_to == self._initial_id, \
                    f"Incoherent CFG: the predecessor block {pred_block_id} must reach block {self._initial_id}"
                pred_block.set_falls_to(self._first_half.block_id)

    def _update_second_half(self):
        # We need to update the corresponding information
        self._second_half.set_comes_from([self._first_half.block_id])
        self._second_half.set_falls_to(self._cfg_block.get_falls_to())
        self._second_half.set_jump_to(self._cfg_block.get_jump_to())
        self._second_half.final_stack_elements = self._cfg_block.final_stack_elements

        # Finally, we update the comes from information from the blocks that are reached afterwards
        initial_jumps_to = self._cfg_block.get_jump_to()
        initial_falls_to = self._cfg_block.get_falls_to()

        if initial_jumps_to is not None:
            self._modify_comes_from(initial_jumps_to, self._second_half.block_id)
        if initial_falls_to is not None:
            self._modify_comes_from(initial_falls_to, self._second_half.block_id)

    def _modify_comes_from(self, block_id: block_id_T, new_pred_block_id: block_id_T):
        """
        Modifies the comes from the block id to replace the id of the initial block with the new one
        """
        block = self._cfg_block_list.blocks[block_id]
        found_previous = False
        comes_from = block.get_comes_from()
        new_comes_from = []
        for pred_block in comes_from:
            if pred_block == self._initial_id:
                found_previous = True
                new_comes_from.append(new_pred_block_id)
            else:
                new_comes_from.append(pred_block)
        block.set_comes_from(new_comes_from)
        assert found_previous, f"Comes from list {comes_from} of {block_id} does not contain {self._initial_id}"

    def __str__(self):
        return f"SplitBlock {self._initial_id} at instruction {self._cfg_instruction}"
