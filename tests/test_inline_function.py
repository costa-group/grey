from hypothesis import given
from parser.cfg_instruction import CFGInstruction
from parser.cfg_block import CFGBlock
from parser.cfg_block_list import CFGBlockList
from parser.cfg_function import CFGFunction
from parser.cfg_object import CFGObject
from cfg_methods.cfg_block_actions.inline_function import InlineFunction
from utils import cfg_instruction_list


class TestInlineFunction:

    @given(cfg_instruction_list(5, 36))
    def test_inline_function_one_function(self, instructions):
        split_list_index = len(instructions) // 12
        cfg_block_0 = CFGBlock("block_0", instructions[:split_list_index], "unconditional", dict())
        cfg_block_1 = CFGBlock("block_1", instructions[split_list_index:2*split_list_index], "unconditional", dict())
        cfg_block_2 = CFGBlock("block_2", instructions[2*split_list_index:3*split_list_index], "unconditional", dict())
        cfg_block_3 = CFGBlock("block_3", instructions[3*split_list_index:4*split_list_index], "conditional", dict())
        cfg_block_4 = CFGBlock("block_4", instructions[4*split_list_index:5*split_list_index], "terminal", dict())
        cfg_block_5 = CFGBlock("block_5", instructions[5*split_list_index:6*split_list_index], "terminal", dict())
        cfg_block_6 = CFGBlock("block_6", instructions[6*split_list_index:7*split_list_index], "conditional", dict())

        function_cfg_block_list = CFGBlockList("f")
        function_cfg_block_list.add_block(cfg_block_0)
        function_cfg_block_list.add_block(cfg_block_1)
        function_cfg_block_list.add_block(cfg_block_2)
        function_cfg_block_list.add_block(cfg_block_3)
        function_cfg_block_list.add_block(cfg_block_4)
        function_cfg_block_list.add_block(cfg_block_5)
        function_cfg_block_list.add_block(cfg_block_6)

        cfg_function = CFGFunction("function", [], [], "block_0", function_cfg_block_list)
        cfg_function.add_exit_point(cfg_block_4.block_id)
        cfg_function.add_exit_point(cfg_block_5.block_id)

        # Function CFG structure:
        #    6
        #  0   1
        #    2
        #    3
        #  4   5
        edges = [(cfg_block_6.block_id, cfg_block_0.block_id, "falls_to"),
                 (cfg_block_6.block_id, cfg_block_1.block_id, "jumps_to"),
                 (cfg_block_0.block_id, cfg_block_2.block_id, "falls_to"),
                 (cfg_block_1.block_id, cfg_block_2.block_id, "jumps_to"),
                 (cfg_block_2.block_id, cfg_block_3.block_id, "jumps_to"),
                 (cfg_block_3.block_id, cfg_block_4.block_id, "falls_to"),
                 (cfg_block_3.block_id, cfg_block_5.block_id, "jumps_to")]

        for u, v, jump_type in edges:
            function_cfg_block_list.blocks[v].add_comes_from(u)
            if jump_type == "jumps_to":
                function_cfg_block_list.blocks[u].set_jump_to(v)
            else:
                function_cfg_block_list.blocks[u].set_falls_to(v)


        # Creation of the main block list
        instruction_call = CFGInstruction("function", [], [])
        cfg_block_7 = CFGBlock("block_7", instructions[7*split_list_index:8*split_list_index], "conditional", dict())
        cfg_block_8 = CFGBlock("block_8", instructions[8*split_list_index:9*split_list_index], "conditional", dict())
        cfg_block_9 = CFGBlock("block_9", [instruction_call] + instructions[9*split_list_index:10*split_list_index], "conditional", dict())
        cfg_block_10 = CFGBlock("block_10", instructions[10*split_list_index:11*split_list_index], "terminal", dict())
        cfg_block_11 = CFGBlock("block_11", instructions[11*split_list_index:], "terminal", dict())

        # We add a call to function in cfg_block_9

        cfg_object_block_list = CFGBlockList()
        cfg_object_block_list.add_block(cfg_block_7)
        cfg_object_block_list.add_block(cfg_block_8)
        cfg_object_block_list.add_block(cfg_block_9)
        cfg_object_block_list.add_block(cfg_block_10)
        cfg_object_block_list.add_block(cfg_block_11)

        # Main CFG structure:
        #  7 8
        #   9
        #  10 11

        edges = [(cfg_block_7.block_id, cfg_block_9.block_id, "jumps_to"),
                 (cfg_block_8.block_id, cfg_block_9.block_id, "jumps_to"),
                 (cfg_block_9.block_id, cfg_block_10.block_id, "falls_to"),
                 (cfg_block_9.block_id, cfg_block_11.block_id, "jumps_to")]

        for u, v, jump_type in edges:
            cfg_object_block_list.blocks[v].add_comes_from(u)
            if jump_type == "jumps_to":
                cfg_object_block_list.blocks[u].set_jump_to(v)
            else:
                cfg_object_block_list.blocks[u].set_falls_to(v)

        # Creation of the CFG object
        cfg_object = CFGObject("object", cfg_object_block_list)
        cfg_object.add_function(cfg_function)

        inline_object = InlineFunction(0, cfg_block_9, cfg_object_block_list, "function", cfg_object)
        inline_object.perform_action()
        assert len(function_cfg_block_list.blocks) == 0, "There must be no sub block in the function"

        # 13 blocks: initial 12 blocks + block 9 split
        assert len(cfg_object_block_list.blocks) == 13, "There must be 13 sub blocks in the function"


        first_split_sub_block = inline_object.first_sub_block
        second_split_sub_block = inline_object.second_sub_block
        # joined_block_id = merged_block_id("block_2", "block_3")
        # assert joined_block_id in function_cfg_block_list.blocks, f"Block {joined_block_id} must appear in the block list"
        # assert joined_block_id == cfg_block_0.get_falls_to(), "Joined block must be the falls to from block 0"
        # assert joined_block_id == cfg_block_1.get_jump_to(), "Joined block must be the jumps to from block 1"
        # assert joined_block_id in cfg_block_4.get_comes_from(), "Joined block must appear in the comes from block 4"
        # assert joined_block_id in cfg_block_5.get_comes_from(), "Joined block must appear in the comes from block 5"
