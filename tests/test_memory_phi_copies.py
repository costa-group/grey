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


class TestConstantPhiArguments:

    def build(self):
        """
        start -> (left, right) -> join, with v9 = phi(0x20: left, a2: right) handled in memory. The constant 0x20 is
        unreachable at the end of left and a2 is reachable at the end of right
        """
        block_list = CFGBlockList("object")
        for block_id in ["start", "left", "right", "join"]:
            instructions = [CFGInstruction("PhiFunction", ["0x20", "a2"], ["v9"])] if block_id == "join" else []
            block = CFGBlock(block_id, instructions, "terminal", dict())
            block.greedy_info = GreedyInfo([], "non_optimal", 0, [])
            block_list.add_block(block)
        for u, v in [("start", "left"), ("start", "right"), ("left", "join"), ("right", "join")]:
            block_list.blocks[v].add_comes_from(u)
            if block_list.blocks[u].get_jump_to() is None:
                block_list.blocks[u].set_jump_to(v)
            else:
                block_list.blocks[u].set_falls_to(v)
        block_list.get_block("join").entries = ["left", "right"]
        block_list.get_block("left").greedy_info.unreachable.add("0x20")
        block_list.get_block("right").greedy_info.reachable["a2"] = (0, 0, True)
        return block_list

    def test_constant_argument_is_pushed_not_stored(self):
        # The constant has no definition to repair: it is only recorded as a constant copy of left, it gets no
        # virtual copy (no VGET to place) and it does not join the phi web (it has no colour)
        from reparation.insert_placeholders import fix_inaccessible_phi_values
        block_list = self.build()
        phi_web = fix_inaccessible_phi_values(block_list, {"v9"}, {"v9": "join"})
        left, right = block_list.get_block("left").greedy_info, block_list.get_block("right").greedy_info
        assert left.constant_copies == {"0x20"}
        assert "0x20" not in left.virtual_copies and left.get_count["0x20"] == 0
        assert "a2" in right.virtual_copies
        assert "0x20" not in phi_web._var2class
        assert "v9" in block_list.get_block("join").greedy_info.phi_defs_to_solve

    def test_constant_copy_is_a_push_in_the_assembly(self):
        from solution_generation.reconstruct_bytecode import id_to_asm_bytecode
        assert id_to_asm_bytecode({}, "PUSH-CONSTANT 0x20")["value"] == "20"
        # The slot addresses keep their format
        assert id_to_asm_bytecode({}, "PUSH 80")["value"] == "80"
