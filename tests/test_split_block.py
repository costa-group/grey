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
        split_object = SplitBlock(selected_index, cfg_block, cfg_block_list)
        split_object.perform_action()
        assert len(cfg_block_list.blocks) == 2, "There must be two sub blocks"
        assert "block_1" in cfg_block_list.blocks, "Block block_1 must appear in the block list"
        assert "block_2" in cfg_block_list.blocks, "Block block_2 must appear in the block list"
        assert len(cfg_block_list.blocks["block_1"].get_instructions()) == selected_index + 1, \
            f"First block must contain {selected_index} instructions"
        n_remaining_instrs = len(cfg_block.get_instructions()) - selected_index - 1
        assert len(cfg_block_list.blocks["block_2"].get_instructions()) == n_remaining_instrs, \
            f"Second block must contain {n_remaining_instrs} instructions"