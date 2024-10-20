from typing import List, Optional
from parser.cfg_block_actions.actions_interface import BlockAction
from parser.cfg_block_actions.utils import modify_comes_from, modify_successors
from parser.cfg_block_list import CFGBlockList
from parser.cfg_block import CFGBlock
from global_params.types import block_id_T


def merged_block_id(block_id_1: block_id_T, block_id_2: block_id_T) -> block_id_T:
    """
    Given the two merged nodes, generates a new name for the resulting split
    """
    return '_merged_'.join([block_id_1, block_id_2])


class MergeBlocks(BlockAction):
    """
    Merges two blocks that belong to the same block list. Keeps the jump type of the second block
    """

    def __init__(self, first_block: CFGBlock, second_block: CFGBlock, cfg_blocklist: CFGBlockList):
        self._first_block: Optional[CFGBlock] = first_block
        self._second_block: Optional[CFGBlock] = second_block
        self._cfg_blocklist: CFGBlockList = cfg_blocklist
        self._combined_block: Optional[CFGBlock] = None
        
        self._first_block_id: block_id_T = first_block.block_id
        self._second_block_id: block_id_T = second_block.block_id

    def perform_action(self):
        combined_instrs = self._first_block.get_instructions() + self._second_block.get_instructions()
        combined_block_id = merged_block_id(self._first_block_id, self._second_block_id)
        # We assume the jump type from the second block
        combined_jump_type = self._second_block.get_jump_type()
        combined_assignment_dict = self._first_block.assignment_dict | self._second_block.assignment_dict

        combined_block = CFGBlock(combined_block_id, combined_instrs, combined_jump_type, combined_assignment_dict)
        self._update_cfg_edges(combined_block)

        # Add the new block to the list of combined blocks
        self._cfg_blocklist.add_block(combined_block)

        # Remove the elements from the block lists and the references
        self._cfg_blocklist.blocks.pop(self._first_block_id)
        self._cfg_blocklist.blocks.pop(self._second_block_id)

        del self._first_block
        del self._second_block

    def _update_cfg_edges(self, combined_block: CFGBlock):
        """
        Updates the CFG in the block list with the information of the combined block
        """
        # Retrieve the information from the first and second blocks
        predecessor_ids = self._first_block.get_comes_from()
        jumps_to_id = self._second_block.get_jump_to()
        falls_to_id = self._second_block.get_falls_to()

        # Update the information from the predecessors of the first block
        for pred_block_id in predecessor_ids:
            modify_successors(pred_block_id, self._first_block_id, combined_block.block_id, self._cfg_blocklist)
        
        # Update the "comes from" information from the successors of the first block
        if jumps_to_id is not None:
            modify_comes_from(jumps_to_id, self._second_block_id, combined_block.block_id, self._cfg_blocklist)
        if falls_to_id is not None:
            modify_comes_from(falls_to_id, self._second_block_id, combined_block.block_id, self._cfg_blocklist)

    def __str__(self):
        return f"MergeBlocks {self._first_block_id} and {self._second_block_id}"
