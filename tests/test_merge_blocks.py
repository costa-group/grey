from hypothesis import given, strategies as st
from parser.cfg_block import CFGBlock
from parser.cfg_block_list import CFGBlockList
from parser.cfg_block_actions.merge_blocks import MergeBlocks, merged_block_id
from utils import cfg_instruction_list


class TestMergeBlocks:

    @given(cfg_instruction_list(6, 24))
    def test_merge_block_simple(self, instructions):
        split_list_index = len(instructions) // 6
        cfg_block_0 = CFGBlock("block_0", instructions[:split_list_index], "unconditional", dict())
        cfg_block_1 = CFGBlock("block_1", instructions[split_list_index:2*split_list_index], "unconditional", dict())
        cfg_block_2 = CFGBlock("block_2", instructions[2*split_list_index:3*split_list_index], "unconditional", dict())
        cfg_block_3 = CFGBlock("block_3", instructions[3*split_list_index:4*split_list_index], "conditional", dict())
        cfg_block_4 = CFGBlock("block_4", instructions[4*split_list_index:5*split_list_index], "terminal", dict())
        cfg_block_5 = CFGBlock("block_5", instructions[5*split_list_index:], "terminal", dict())

        cfg_block_list = CFGBlockList()
        cfg_block_list.add_block(cfg_block_0)
        cfg_block_list.add_block(cfg_block_1)
        cfg_block_list.add_block(cfg_block_2)
        cfg_block_list.add_block(cfg_block_3)
        cfg_block_list.add_block(cfg_block_4)
        cfg_block_list.add_block(cfg_block_5)

        # CFG structure:
        #  0   1
        #    2
        #    3
        #  4   5
        edges = [(cfg_block_0.block_id, cfg_block_2.block_id, "falls_to"),
                 (cfg_block_1.block_id, cfg_block_2.block_id, "jumps_to"),
                 (cfg_block_2.block_id, cfg_block_3.block_id, "jumps_to"),
                 (cfg_block_3.block_id, cfg_block_4.block_id, "falls_to"),
                 (cfg_block_3.block_id, cfg_block_5.block_id, "jumps_to")]

        for u, v, jump_type in edges:
            cfg_block_list.blocks[v].add_comes_from(u)
            if jump_type == "jumps_to":
                cfg_block_list.blocks[u].set_jump_to(v)
            else:
                cfg_block_list.blocks[u].set_falls_to(v)

        merge_object = MergeBlocks(cfg_block_2, cfg_block_3, cfg_block_list)
        merge_object.perform_action()
        assert len(cfg_block_list.blocks) == 5, "There must be five sub blocks"
        # At this point, the blocks are erased
        joined_block_id = merged_block_id("block_2", "block_3")
        assert joined_block_id in cfg_block_list.blocks, f"Block {joined_block_id} must appear in the block list"
        assert joined_block_id == cfg_block_0.get_falls_to(), "Joined block must be the falls to from block 0"
        assert joined_block_id == cfg_block_1.get_jump_to(), "Joined block must be the jumps to from block 1"
        assert joined_block_id in cfg_block_4.get_comes_from(), "Joined block must appear in the comes from block 4"
        assert joined_block_id in cfg_block_5.get_comes_from(), "Joined block must appear in the comes from block 5"
