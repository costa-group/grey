from typing import Optional
from parser.cfg_block_actions.actions_interface import BlockAction
from parser.cfg_block_actions.split_block import SplitBlock
from parser.cfg_block_list import CFGBlockList
from parser.cfg_block import CFGBlock
from parser.cfg_function import CFGFunction
from parser.cfg_object import CFGObject
from parser.cfg_block_actions.utils import modify_comes_from, modify_successors


class InlineFunction(BlockAction):
    """
    Action for performing inlining of a different block list into an existing one.
    """

    def __init__(self, instr_position: int, cfg_block: CFGBlock, cfg_blocklist: CFGBlockList,
                 function_name: str, cfg_object: CFGObject):
        """
        It receives the position in which we want to split, the corresponding block in which we are appending
        the corresponding block list, its block list, the function name and the block list
        associated to this function name
        """
        self._instr_position: int = instr_position
        self._cfg_block: CFGBlock = cfg_block
        self._cfg_blocklist: CFGBlockList = cfg_blocklist
        self._function_name: str = function_name
        self._cfg_function: CFGFunction = cfg_object.functions[function_name]
        self._function_blocklist: CFGBlockList = self._cfg_function.blocks
        self._cfg_object: CFGObject = cfg_object
        self._first_sub_block: Optional[CFGObject] = None
        self._second_sub_block: Optional[CFGObject] = None

    def perform_action(self):
        original_block_id = self._cfg_block.block_id

        # First we need to split the block in the function call, which is given by the instr position.
        # As a final check, we ensure the instruction in that position corresponds to the function name passed as
        # an argument
        assert self._cfg_block.get_instructions()[self._instr_position].get_op_name() == self._function_name, \
            f"Expected function call {self._function_name} in position {self._instr_position} but got instead" \
            f"{self._cfg_block.get_instructions()}"

        # Include the blocks from the function into the CFG block list
        for block in self._function_blocklist.blocks.values():
            self._cfg_blocklist.add_block(block)

        function_start_id = self._cfg_function.blocks.start_block
        function_exists_ids = self._cfg_function.blocks.terminal_blocks

        # Even after splitting the blocks, we have to remove the first instruction
        # from the first block (the function call)
        split_action = SplitBlock(self._instr_position, self._cfg_block, self._cfg_blocklist)
        split_action.perform_action()

        first_sub_block = split_action.first_half
        # We have to remove the function call
        first_sub_block.remove_instruction(-1)
        second_sub_block = split_action.second_half

        self._first_sub_block = first_sub_block
        self._second_sub_block = second_sub_block

        # For now, we only connect the blocks without considering if some of them could be empty
        # We need to modify both the comes from and the falls to/jumps to fields of the start and exits field and the
        # halves
        modify_successors(first_sub_block.block_id, second_sub_block.block_id, function_start_id, self._cfg_blocklist)
        modify_comes_from(function_start_id, None, first_sub_block.block_id, self._cfg_blocklist)

        # We set the "comes_from" from the second block to empty. This way, we can ensure only the terminal blocks
        # appear in this list
        self._cfg_blocklist.blocks[second_sub_block.block_id].set_comes_from([])
        for exit_id in function_exists_ids:
            # Now the exit id must jump to the second sub_block
            modify_successors(exit_id, None, second_sub_block.block_id, self._cfg_blocklist)
            self._cfg_blocklist.blocks[second_sub_block.block_id].add_comes_from(exit_id)

        # Last step consists of removing the blocklist, the function and remove the function
        # from the corresponding object
        self._function_blocklist.blocks.clear()
        del self._function_blocklist
        del self._cfg_function
        self._cfg_object.functions.pop(self._function_name)

        # Last step is to check whether the current block list updates the start block correctly
        if self._cfg_blocklist.start_block == original_block_id:
            self._cfg_blocklist.start_block = self.first_sub_block.block_id

    @property
    def first_sub_block(self) -> Optional[CFGBlock]:
        """
        First sub block after splitting the function call. Only contains a None value if the
        action has not been performed yet
        """
        return self._first_sub_block

    @property
    def second_sub_block(self) -> Optional[CFGBlock]:
        """
        Second sub block after splitting the function call. Only contains a None value if the
        actions has not been performed yet
        """
        return self._second_sub_block

    def __str__(self):
        return f"Inlining function {self._function_name}"
