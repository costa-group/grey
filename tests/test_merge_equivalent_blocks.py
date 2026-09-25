from typing import List, Tuple
from parser.cfg_block import CFGBlock
from parser.cfg_block_list import CFGBlockList
from parser.cfg_instruction import CFGInstruction
from cfg_methods.equivalent_blocks_merging import merge_equivalent_blocks_block_list, FreshVariables

# Long enough error message so that merging is always profitable
LONG_CONSTANT = "0x" + "ab" * 32


def revert_block(block_id: str, value: str, jump_type: str = "terminal") -> CFGBlock:
    """
    Block that stores the value together with a long constant and reverts
    """
    instructions = [CFGInstruction("mstore", [LONG_CONSTANT, "0x00"], []),
                    CFGInstruction("mstore", [value, "0x20"], []),
                    CFGInstruction("revert", ["0x40", "0x00"], [])]
    return CFGBlock(block_id, instructions, jump_type, dict())


def build_block_list(blocks: List[CFGBlock], edges: List[Tuple[str, str, str]]) -> CFGBlockList:
    """
    The first block is the start block. Edges are (source, target, "jumps_to" | "falls_to")
    """
    block_list = CFGBlockList("object")
    for block in blocks:
        block_list.add_block(block)
    for u, v, jump_type in edges:
        block_list.blocks[v].add_comes_from(u)
        if jump_type == "jumps_to":
            block_list.blocks[u].set_jump_to(v)
        else:
            block_list.blocks[u].set_falls_to(v)
    return block_list


def survivor(block_list: CFGBlockList, block_id_1: str, block_id_2: str) -> str:
    """
    Exactly one of the two merged blocks remains in the block list
    """
    assert (block_id_1 in block_list.blocks) != (block_id_2 in block_list.blocks)
    return block_id_1 if block_id_1 in block_list.blocks else block_id_2


def merge(block_list: CFGBlockList) -> int:
    return merge_equivalent_blocks_block_list(block_list, FreshVariables({"v0", "v1", "v2", "v3", "v4"}))


def check_coherence(block_list: CFGBlockList) -> None:
    """
    The successors and predecessors are coherent, phi-functions have one argument per entry and
    the predecessors of a block with several predecessors have a single successor
    """
    for block_id, block in block_list.blocks.items():
        for successor in block.successors:
            assert block_id in block_list.get_block(successor).get_comes_from()
        for pred in block.get_comes_from():
            assert block_id in block_list.get_block(pred).successors
            if len(block.get_comes_from()) > 1:
                assert len(block_list.get_block(pred).successors) == 1
        for phi_instr in block.phi_instructions():
            assert len(phi_instr.get_in_args()) == len(block.entries)
            assert sorted(block.entries) == sorted(block.get_comes_from())
    check_coherence_joins(block_list)


def check_coherence_joins(block_list: CFGBlockList) -> None:
    """
    Same as check_coherence, but allowing a predecessor to reach one block with several predecessors
    """
    for block_id, block in block_list.blocks.items():
        for successor in block.successors:
            assert block_id in block_list.get_block(successor).get_comes_from()
        joins = [successor for successor in block.successors
                 if len(block_list.get_block(successor).get_comes_from()) > 1]
        assert len(joins) <= 1


def diamond_with_reverts(value_left: str, value_right: str, right_block: CFGBlock = None) -> CFGBlockList:
    """
    start -> (left, right), each of them computing a value and reverting in a different block
    """
    start = CFGBlock("start", [CFGInstruction("calldataload", ["0x00"], ["v0"])], "conditional", dict())
    start.set_condition("v0")
    left = CFGBlock("left", [CFGInstruction("calldataload", ["0x20"], ["v1"])], "unconditional", dict())
    right = CFGBlock("right", [CFGInstruction("calldataload", ["0x40"], ["v2"])], "unconditional", dict())
    revert_left = revert_block("revert_left", value_left)
    revert_right = right_block if right_block is not None else revert_block("revert_right", value_right)
    return build_block_list([start, left, right, revert_left, revert_right],
                            [("start", "left", "falls_to"), ("start", "right", "jumps_to"),
                             ("left", "revert_left", "jumps_to"), ("right", "revert_right", "jumps_to")])


class TestMergeEquivalentBlocks:

    def test_merge_terminal_blocks_with_phi(self):
        block_list = diamond_with_reverts("v1", "v2")
        assert merge(block_list) == 1
        merged_id = survivor(block_list, "revert_left", "revert_right")
        merged_block = block_list.get_block(merged_id)
        assert block_list.get_block("left").get_jump_to() == merged_id
        assert block_list.get_block("right").get_jump_to() == merged_id
        assert sorted(merged_block.get_comes_from()) == ["left", "right"]

        # A phi-function combines v1 and v2, and it is used instead of v1
        phi_instrs = merged_block.phi_instructions()
        assert len(phi_instrs) == 1
        phi_var = phi_instrs[0].get_out_args()[0]
        assert dict(zip(merged_block.entries, phi_instrs[0].get_in_args())) == {"left": "v1", "right": "v2"}
        used_vars = [arg for instr in merged_block.instructions_without_phi_functions() for arg in instr.get_in_args()]
        assert phi_var in used_vars and "v1" not in used_vars
        assert block_list.terminal_blocks == [merged_id]
        check_coherence(block_list)

    def test_merge_same_variable_no_phi(self):
        block_list = diamond_with_reverts("v0", "v0")
        assert merge(block_list) == 1
        merged_id = survivor(block_list, "revert_left", "revert_right")
        assert len(block_list.get_block(merged_id).phi_instructions()) == 0
        check_coherence(block_list)

    def test_different_instructions_not_merged(self):
        different = revert_block("revert_right", "v2")
        different.get_instructions()[0] = CFGInstruction("mstore", ["0x" + "cd" * 32, "0x00"], [])
        block_list = diamond_with_reverts("v1", "v2", different)
        assert merge(block_list) == 0
        assert "revert_right" in block_list.blocks

    def test_non_bijective_not_merged(self):
        # add(v1, v0) vs add(v2, v2): the correspondence is not one-to-one
        left = CFGBlock("revert_left", [CFGInstruction("add", ["v1", "v0"], ["v3"]),
                                        CFGInstruction("mstore", [LONG_CONSTANT, "v3"], []),
                                        CFGInstruction("revert", ["0x40", "0x00"], [])], "terminal", dict())
        right = CFGBlock("revert_right", [CFGInstruction("add", ["v2", "v2"], ["v4"]),
                                          CFGInstruction("mstore", [LONG_CONSTANT, "v4"], []),
                                          CFGInstruction("revert", ["0x40", "0x00"], [])], "terminal", dict())
        block_list = diamond_with_reverts("v1", "v2", right)
        block_list.remove_block("revert_left")
        left.set_comes_from(["left"])
        block_list.add_block(left)
        assert merge(block_list) == 0

    def test_two_levels_merged(self):
        # start -> (a, a'), a -> t, a' -> t', where t ~ t' and a ~ a'
        start = CFGBlock("start", [CFGInstruction("calldataload", ["0x00"], ["v0"])], "conditional", dict())
        start.set_condition("v0")
        a = CFGBlock("a", [CFGInstruction("calldataload", ["0x20"], ["v1"]),
                           CFGInstruction("mstore", [LONG_CONSTANT, "0x60"], [])], "unconditional", dict())
        a_prime = CFGBlock("a_prime", [CFGInstruction("calldataload", ["0x20"], ["v2"]),
                                       CFGInstruction("mstore", [LONG_CONSTANT, "0x60"], [])], "unconditional", dict())
        block_list = build_block_list([start, a, a_prime, revert_block("t", "v1"), revert_block("t_prime", "v2")],
                                      [("start", "a", "falls_to"), ("start", "a_prime", "jumps_to"),
                                       ("a", "t", "jumps_to"), ("a_prime", "t_prime", "jumps_to")])
        # t' merged into t, but a and a' share the predecessor start, so they are kept
        assert merge(block_list) == 1
        merged_id = survivor(block_list, "t", "t_prime")
        assert set(block_list.blocks) == {"start", "a", "a_prime", merged_id}
        check_coherence(block_list)

    def test_chain_merged_and_phi_collapses(self):
        # p1 -> a -> t, p2 -> a' -> t', with distinct predecessors p1, p2 of a, a'
        start = CFGBlock("start", [CFGInstruction("calldataload", ["0x00"], ["v0"])], "conditional", dict())
        start.set_condition("v0")
        p1 = CFGBlock("p1", [], "unconditional", dict())
        p2 = CFGBlock("p2", [], "unconditional", dict())
        a = CFGBlock("a", [CFGInstruction("calldataload", ["0x20"], ["v1"]),
                           CFGInstruction("mstore", [LONG_CONSTANT, "0x60"], [])], "unconditional", dict())
        a_prime = CFGBlock("a_prime", [CFGInstruction("calldataload", ["0x20"], ["v2"]),
                                       CFGInstruction("mstore", [LONG_CONSTANT, "0x60"], [])], "unconditional", dict())
        block_list = build_block_list([start, p1, p2, a, a_prime, revert_block("t", "v1"),
                                       revert_block("t_prime", "v2")],
                                      [("start", "p1", "falls_to"), ("start", "p2", "jumps_to"),
                                       ("p1", "a", "jumps_to"), ("p2", "a_prime", "jumps_to"),
                                       ("a", "t", "jumps_to"), ("a_prime", "t_prime", "jumps_to")])
        assert merge(block_list) == 2
        merged_a = survivor(block_list, "a", "a_prime")
        merged_t = survivor(block_list, "t", "t_prime")
        assert set(block_list.blocks) == {"start", "p1", "p2", merged_a, merged_t}
        assert sorted(block_list.get_block(merged_a).get_comes_from()) == ["p1", "p2"]
        # The merged t only has a single predecessor, so the phi-function is removed and its output
        # replaced by the value computed in the merged a
        t = block_list.get_block(merged_t)
        assert t.get_comes_from() == [merged_a]
        assert t.phi_instructions() == []
        value_a = block_list.get_block(merged_a).get_instructions()[0].get_out_args()[0]
        assert value_a in [arg for instr in t.get_instructions() for arg in instr.get_in_args()]
        check_coherence(block_list)

    def test_critical_edges_are_split(self):
        # start -> (r1, x), x -> (r2, y): r1 and r2 are reached from conditional jumps
        start = CFGBlock("start", [CFGInstruction("calldataload", ["0x00"], ["v0"])], "conditional", dict())
        start.set_condition("v0")
        x = CFGBlock("x", [CFGInstruction("calldataload", ["0x20"], ["v1"])], "conditional", dict())
        x.set_condition("v1")
        y = CFGBlock("y", [CFGInstruction("stop", [], [])], "terminal", dict())
        block_list = build_block_list([start, x, revert_block("r1", "v0"), revert_block("r2", "v0"), y],
                                      [("start", "r1", "jumps_to"), ("start", "x", "falls_to"),
                                       ("x", "r2", "jumps_to"), ("x", "y", "falls_to")])
        assert merge(block_list) == 1
        merged_id = survivor(block_list, "r1", "r2")
        assert block_list.get_block("start").get_jump_to() == f"start_to_{merged_id}"
        assert block_list.get_block("x").get_jump_to() == f"x_to_{merged_id}"
        assert sorted(block_list.get_block(merged_id).get_comes_from()) == [f"start_to_{merged_id}",
                                                                          f"x_to_{merged_id}"]
        check_coherence(block_list)

    def test_single_falling_predecessor(self):
        # p1 and p2 are empty blocks that fall to r1 and r2 respectively: only one of them can keep
        # falling to the merged block
        start = CFGBlock("start", [CFGInstruction("calldataload", ["0x00"], ["v0"])], "conditional", dict())
        start.set_condition("v0")
        p1 = CFGBlock("p1", [], "falls_to", dict())
        p2 = CFGBlock("p2", [], "falls_to", dict())
        block_list = build_block_list([start, p1, p2, revert_block("r1", "v0"), revert_block("r2", "v0")],
                                      [("start", "p1", "falls_to"), ("start", "p2", "jumps_to"),
                                       ("p1", "r1", "falls_to"), ("p2", "r2", "falls_to")])
        assert merge(block_list) == 1
        merged_id = survivor(block_list, "r1", "r2")
        falls_to = [block_list.get_block("p1").get_falls_to(), block_list.get_block("p2").get_falls_to()]
        assert merged_id in falls_to
        edge_block_id = [block_id for block_id in falls_to if block_id != merged_id][0]
        assert block_list.get_block(edge_block_id).get_jump_to() == merged_id
        assert len([pred for pred in block_list.get_block(merged_id).get_comes_from()
                    if block_list.get_block(pred).get_falls_to() == merged_id]) == 1
        check_coherence(block_list)

    def test_blocks_reaching_loops_not_merged(self):
        # p1 -> a -> loop, p2 -> a' -> loop: a and a' would be merged if the loop were a terminal block
        start = CFGBlock("start", [CFGInstruction("calldataload", ["0x00"], ["v0"])], "conditional", dict())
        start.set_condition("v0")
        p1 = CFGBlock("p1", [], "unconditional", dict())
        p2 = CFGBlock("p2", [], "unconditional", dict())
        a = CFGBlock("a", [CFGInstruction("mstore", [LONG_CONSTANT, "0x60"], [])], "unconditional", dict())
        a_prime = CFGBlock("a_prime", [CFGInstruction("mstore", [LONG_CONSTANT, "0x60"], [])], "unconditional",
                           dict())
        loop = CFGBlock("loop", [CFGInstruction("calldataload", ["0x00"], ["v3"])], "conditional", dict())
        loop.set_condition("v3")
        exit_block = CFGBlock("exit", [CFGInstruction("stop", [], [])], "terminal", dict())
        block_list = build_block_list([start, p1, p2, a, a_prime, loop, exit_block],
                                      [("start", "p1", "falls_to"), ("start", "p2", "jumps_to"),
                                       ("p1", "a", "jumps_to"), ("p2", "a_prime", "jumps_to"),
                                       ("a", "loop", "jumps_to"), ("a_prime", "loop", "jumps_to"),
                                       ("loop", "loop", "jumps_to"), ("loop", "exit", "falls_to")])
        assert merge(block_list) == 0
        assert "a_prime" in block_list.blocks

    def test_small_blocks_not_merged(self):
        # revert(0, v) with a different v in each block: moving the value of the phi-function costs more
        # than the block itself
        start = CFGBlock("start", [CFGInstruction("calldataload", ["0x00"], ["v0"])], "conditional", dict())
        start.set_condition("v0")
        x = CFGBlock("x", [CFGInstruction("calldataload", ["0x20"], ["v1"])], "conditional", dict())
        x.set_condition("v1")
        r1 = CFGBlock("r1", [CFGInstruction("revert", ["v0", "0x00"], [])], "terminal", dict())
        r2 = CFGBlock("r2", [CFGInstruction("revert", ["v1", "0x00"], [])], "terminal", dict())
        y = CFGBlock("y", [CFGInstruction("stop", [], [])], "terminal", dict())
        block_list = build_block_list([start, x, r1, r2, y],
                                      [("start", "r1", "jumps_to"), ("start", "x", "falls_to"),
                                       ("x", "r2", "jumps_to"), ("x", "y", "falls_to")])
        assert merge(block_list) == 0
