from greedy.greedy_info import GreedyInfo
from parser.cfg_block import CFGBlock
from parser.cfg_block_list import CFGBlockList
from parser.cfg_instruction import CFGInstruction
from reparation.memory_liveness import memory_definition_blocks, phi_copies_from_memory


def build_block_list(greedy_ids_per_block, edges):
    """
    Block list whose blocks only contain the given pseudo greedy ids. The first block is the start one.
    Block "join" has the phi v9 = phi(a1: left, a2: right), handled in memory
    """
    block_list = CFGBlockList("object")
    for block_id in greedy_ids_per_block:
        instructions = [CFGInstruction("PhiFunction", ["a1", "a2"], ["v9"])] if block_id == "join" else []
        block = CFGBlock(block_id, instructions, "terminal", dict())
        block.greedy_info = GreedyInfo(greedy_ids_per_block[block_id], "non_optimal", 0, [])
        block_list.add_block(block)
    for u, v in edges:
        block_list.blocks[v].add_comes_from(u)
        if block_list.blocks[u].get_jump_to() is None:
            block_list.blocks[u].set_jump_to(v)
        else:
            block_list.blocks[u].set_falls_to(v)
    join = block_list.get_block("join")
    join.entries = ["left", "right"]
    join.greedy_info.phi_defs_to_solve.add("v9")
    return block_list


class TestMemoryPhiCopies:

    def test_argument_stored_in_dominating_block_is_read_from_memory(self):
        # a1 is stored in start, which dominates left: the copy at the end of left reads its slot
        block_list = build_block_list({"start": ["DUP-VSET(a1,0)"], "left": [], "right": [], "join": ["VGET(v9)"]},
                                      [("start", "left"), ("start", "right"), ("left", "join"), ("right", "join")])
        definitions = memory_definition_blocks(block_list)
        assert phi_copies_from_memory(block_list, "left", definitions) == [("join", "v9", "a1")]

    def test_argument_stored_in_another_path_is_copied_from_the_stack(self):
        # a2 is only stored after the join (in "after"), so its slot does not hold it at the end of right: the
        # copy must be done from the stack
        block_list = build_block_list({"start": [], "left": [], "right": [], "join": ["VGET(v9)"],
                                       "after": ["DUP-VSET(a2,0)", "VGET(a2)"]},
                                      [("start", "left"), ("start", "right"), ("left", "join"), ("right", "join"),
                                       ("join", "after")])
        definitions = memory_definition_blocks(block_list)
        assert definitions["a2"] == "after"
        assert phi_copies_from_memory(block_list, "right", definitions) == []
