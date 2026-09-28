import global_params.constants as constants
from greedy.utils import detect_blocks_with_multiple_insertion
from parser.cfg_block import CFGBlock
from parser.cfg_block_list import CFGBlockList
from parser.cfg_instruction import CFGInstruction


def call_then_successor(successor_src_ws):
    """
    start (sub_block) calls f, which returns 10 values; its successor "after" starts with successor_src_ws
    """
    outputs = [f"v{i}" for i in range(10)]
    call = CFGInstruction("f", [], outputs)
    start = CFGBlock("start", [call], "sub_block", dict())
    start.split_instruction = call
    after = CFGBlock("after", [CFGInstruction("revert", ["0x00", "0x00"], [])], "terminal", dict())
    block_list = CFGBlockList("object")
    block_list.add_block(start)
    block_list.add_block(after)
    start.set_falls_to("after")
    after.add_comes_from("start")
    start.spec = {"src_ws": [], "tgt_ws": outputs, "user_instrs": []}
    after.spec = {"src_ws": successor_src_ws, "tgt_ws": [], "user_instrs": []}
    return block_list


class TestMultipleInsertion:

    def test_elements_beyond_the_reachable_depth_are_moved(self, monkeypatch):
        monkeypatch.setattr(constants, "MAX_STACK_DEPTH", 8)
        block_list = call_then_successor([f"v{i}" for i in range(10)])
        assert detect_blocks_with_multiple_insertion(block_list) == {"after": 2}

    def test_dead_outputs_left_as_junk_are_not_moved(self, monkeypatch):
        # The successor does not use the results (e.g. InboxStub in 0x8e83db08...): its stack is empty
        monkeypatch.setattr(constants, "MAX_STACK_DEPTH", 8)
        block_list = call_then_successor([])
        assert detect_blocks_with_multiple_insertion(block_list) == {}
