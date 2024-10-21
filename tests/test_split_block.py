from hypothesis import given, strategies as st
from parser.cfg_block_actions.split_block import CFGBlock, CFGInstruction, CFGBlockList, SplitBlock
from utils import cfg_instruction_list


class TestSplitBlock:

    @given(st.integers(), cfg_instruction_list())
    def test_split_block_simple(self, n, instructions):
        # Simple example: just one block
        cfg_block = CFGBlock("block_0", instructions, "sub_block", dict())
        cfg_block_list = CFGBlockList()
        cfg_block_list.add_block(cfg_block)

        # We don't want to select the last index
        selected_index = (n % (len(instructions) - 1))
        split_object = SplitBlock(instructions[selected_index], cfg_block, cfg_block_list)
        split_object.perform_action()
        assert True
