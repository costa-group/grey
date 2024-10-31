from typing import Optional, Dict
from global_params.types import block_id_T, function_name_T, var_id_T
from parser.cfg_block_actions.actions_interface import BlockAction
from parser.cfg_block_actions.split_block import SplitBlock
from parser.cfg_instruction import CFGInstruction
from parser.cfg_block_list import CFGBlockList
from parser.cfg_block import CFGBlock
from parser.cfg_function import CFGFunction
from parser.cfg_object import CFGObject
from parser.cfg_block_actions.utils import modify_comes_from, modify_successors
from analysis.cfg_validation import validate_block_list_comes_from


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
        self._function_name: function_name_T = function_name
        self._cfg_function: CFGFunction = cfg_object.functions[function_name]
        self._function_blocklist: CFGBlockList = self._cfg_function.blocks
        self._cfg_object: CFGObject = cfg_object
        self._first_sub_block: Optional[CFGObject] = None
        self._second_sub_block: Optional[CFGObject] = None

    def perform_action(self):
        call_instruction = self._cfg_block.get_instructions()[self._instr_position]

        # First we need to split the block in the function call, which is given by the instr position.
        # As a final check, we ensure the instruction in that position corresponds to the function name passed as
        # an argument
        assert call_instruction.get_op_name() == self._function_name, \
            f"Expected function call {self._function_name} in position {self._instr_position} but got instead" \
            f"{self._cfg_block.get_instructions()}"

        # Rename the input and output values in the function block list to match the returned values
        self._rename_output_values(call_instruction)

        # Include the blocks from the function into the CFG block list
        for block in self._function_blocklist.blocks.values():

            # Blocks that are introduced are no longer return functions. Hence, we need to modify them before
            # adding to the block list so that they are not registered as terminal blocks
            # (now they jump to the return block)
            if block.get_jump_type() == "FunctionReturn":
                block.set_jump_type("unconditional")

            self._cfg_blocklist.add_block(block)

        function_start_id = self._cfg_function.blocks.start_block
        function_exists_ids = self._cfg_function.blocks.function_return_blocks

        # Even after splitting the blocks, we have to remove the first instruction
        # from the first block (the function call)
        split_action = SplitBlock(self._instr_position, self._cfg_block, self._cfg_blocklist)
        split_action.perform_action()

        first_sub_block = split_action.first_half
        # We have to remove the function call
        call_instruction = first_sub_block.remove_instruction(-1)
        second_sub_block = split_action.second_half

        self._first_sub_block = first_sub_block
        self._second_sub_block = second_sub_block

        # For now, we only connect the blocks without considering if some of them could be empty
        # We need to modify both the comes from and the falls to/jumps to fields of the start and exits field and the
        # halves
        modify_successors(first_sub_block.block_id, second_sub_block.block_id, function_start_id, self._cfg_blocklist)
        modify_comes_from(function_start_id, None, first_sub_block.block_id, self._cfg_blocklist)

        # Returned values correspond to the input values of the last instruction of each exit block,
        # as they must correspond to the instruction "functionReturn"
        returned_values_per_exit = []

        # We set the "comes_from" from the second block to empty. This way, we can ensure only the terminal blocks
        # appear in this list
        self._cfg_blocklist.blocks[second_sub_block.block_id].set_comes_from([])
        for exit_id in function_exists_ids:
            # Now the exit id must jump to the second sub_block
            modify_successors(exit_id, None, second_sub_block.block_id, self._cfg_blocklist)

            # Add the exit id if it doesn't appear yet
            if exit_id not in second_sub_block.get_comes_from():
                second_sub_block.add_comes_from(exit_id)

            exit_block = self._cfg_blocklist.get_block(exit_id)
            last_instruction_exit = exit_block.get_instructions()[-1]
            assert last_instruction_exit.get_op_name() == "functionReturn", \
                f"Last instruction of block {exit_id} is not a FunctionReturn"
            returned_values_per_exit.append(last_instruction_exit.get_in_args())

            # Finally, we remove the function return from the exit id
            exit_block.remove_instruction(-1)

        if len(returned_values_per_exit) > 1:
            # We need to assign phi-functions for the values that were assigned to the returned instruction
            for i, output_values in enumerate(call_instruction.get_out_args()):

                returned_values_i = [returned_value[i] for returned_value in returned_values_per_exit]

                # Insert phi function at the beginning
                second_sub_block.insert_instruction(0, CFGInstruction("PhiFunction", returned_values_i, [output_values]))

        # is_correct, reason = validate_block_list_comes_from(self._cfg_blocklist)

        # Last step consists of removing the blocklist, the function and remove the function
        # from the corresponding object
        self._function_blocklist.blocks.clear()
        del self._function_blocklist
        del self._cfg_function
        self._cfg_object.functions.pop(self._function_name)

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

    def _rename_output_values(self, call_instruction: CFGInstruction) -> None:
        """
        When inlining, the name of the input and output values must match the ones that are passed as arguments
        """
        relabel_dict = self._relabel_dict_from_call_instruction(call_instruction)

        # Traverse all blocks and rename them using the relabel dict
        for block in self._cfg_function.blocks.blocks.values():
            for instruction in block.get_instructions():
                instruction.in_args = [relabel_dict.get(in_arg, in_arg) for in_arg in instruction.in_args]
                instruction.out_args = [relabel_dict.get(out_arg, out_arg) for out_arg in instruction.out_args]

    def _relabel_dict_from_call_instruction(self, call_instruction: CFGInstruction):
        """
        Map the intput and output values of terminal blocks
        """
        assert len(self._cfg_function.arguments) == len(call_instruction.get_in_args()), \
            f"The number of arguments of function {call_instruction.get_op_name()} do not match the expected ones"

        relabel_dict = {arg: in_var for arg, in_var in zip(self._cfg_function.arguments, call_instruction.get_in_args())}
        for exit_block_id in self._cfg_function.blocks.function_return_blocks:
            exit_block = self._cfg_function.blocks.get_block(exit_block_id)
            last_instruction = exit_block.get_instructions()[-1]
            assert last_instruction.get_op_name() == "functionReturn", \
                f"Last instruction of exit block {exit_block_id} must correspond to a function return"

            # Recall that the variables returned corresponds to the input variables of function return
            assert len(last_instruction.get_in_args()) == len(call_instruction.get_out_args()), \
                f"The number of returned values of {exit_block_id} do not match the expected ones"

            relabel_dict.update({arg: out_var for arg, out_var in zip(last_instruction.get_in_args(),
                                                                      call_instruction.get_out_args())})

        return relabel_dict

    def __str__(self):
        return f"Inlining function {self._function_name}"
