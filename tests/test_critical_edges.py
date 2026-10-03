from parser.cfg_block import CFGBlock
from parser.cfg_block_list import CFGBlockList
from parser.cfg_instruction import CFGInstruction
from cfg_methods.critical_edges import split_critical_edges_block_list
from solution_generation.reconstruct_bytecode import removable_edge_blocks


def build_block_list(blocks, edges):
    """
    The first block is the start one. Edges are (source, target, "jumps_to" | "falls_to")
    """
    block_list = CFGBlockList("object")
    for block in blocks:
        block_list.add_block(block)
    for u, v, kind in edges:
        block_list.blocks[v].add_comes_from(u)
        if kind == "jumps_to":
            block_list.blocks[u].set_jump_to(v)
        else:
            block_list.blocks[u].set_falls_to(v)
    return block_list


def if_without_else():
    """
    cond -> (then, join), then -> join; join has the phi v3 = phi(v1: cond, v2: then)
    """
    cond = CFGBlock("cond", [CFGInstruction("calldataload", ["0x00"], ["v0"])], "conditional", dict())
    cond.set_condition("v0")
    then = CFGBlock("then", [CFGInstruction("calldataload", ["0x20"], ["v2"])], "unconditional", dict())
    join = CFGBlock("join", [CFGInstruction("PhiFunction", ["v1", "v2"], ["v3"]),
                             CFGInstruction("stop", [], [])], "terminal", dict())
    block_list = build_block_list([cond, then, join], [("cond", "then", "jumps_to"), ("cond", "join", "falls_to"),
                                                       ("then", "join", "jumps_to")])
    join.entries = ["cond", "then"]
    return block_list


class TestCriticalEdges:

    def test_if_without_else_is_split(self):
        block_list = if_without_else()
        assert split_critical_edges_block_list(block_list) == 1
        edge_block = block_list.get_block("cond_to_join")
        assert edge_block.is_edge_block and edge_block.splits_critical_edge
        assert block_list.get_block("cond").get_falls_to() == "cond_to_join"
        assert edge_block.get_jump_to() == "join"
        join = block_list.get_block("join")
        # The phi argument for the edge now comes from the edge block
        assert join.entries == ["cond_to_join", "then"]
        assert sorted(join.get_comes_from()) == ["cond_to_join", "then"]

    def test_diamond_and_loop_unchanged(self):
        # Diamond: cond -> (a, b), a -> join, b -> join (no critical edge)
        cond = CFGBlock("cond", [], "conditional", dict())
        cond.set_condition("0x01")
        blocks = [cond, CFGBlock("a", [], "unconditional", dict()), CFGBlock("b", [], "unconditional", dict()),
                  CFGBlock("join", [CFGInstruction("stop", [], [])], "terminal", dict())]
        diamond = build_block_list(blocks, [("cond", "a", "jumps_to"), ("cond", "b", "falls_to"),
                                            ("a", "join", "jumps_to"), ("b", "join", "jumps_to")])
        assert split_critical_edges_block_list(diamond) == 0

        # Loop: entry -> header, header -> (body, exit), body -> header (the latch jumps unconditionally)
        header = CFGBlock("header", [], "conditional", dict())
        header.set_condition("0x01")
        blocks = [CFGBlock("entry", [], "unconditional", dict()), header,
                  CFGBlock("body", [], "unconditional", dict()),
                  CFGBlock("exit", [CFGInstruction("stop", [], [])], "terminal", dict())]
        loop = build_block_list(blocks, [("entry", "header", "jumps_to"), ("header", "body", "jumps_to"),
                                         ("header", "exit", "falls_to"), ("body", "header", "jumps_to")])
        assert split_critical_edges_block_list(loop) == 0

    def test_empty_edge_blocks_are_skipped(self):
        block_list = if_without_else()
        split_critical_edges_block_list(block_list)
        tags = {"then": 1, "join": 2, "cond_to_join": 3}
        for block in block_list.blocks.values():
            block.greedy_ids = []
        block_list.get_block("cond_to_join").greedy_ids = ["PUSH [TAG]_0"]
        redirect, _ = removable_edge_blocks(block_list.blocks, tags)
        # cond falls to the edge block and nothing else falls to join: cond falls directly to join
        assert redirect == {"cond_to_join": "join"}

    def test_edge_block_kept_if_successor_already_reached_by_falls_to(self):
        block_list = if_without_else()
        split_critical_edges_block_list(block_list)
        # then falls to join, so cond cannot fall to join as well
        then = block_list.get_block("then")
        then.set_falls_to(then.get_jump_to())
        then.set_jump_to(None)
        for block in block_list.blocks.values():
            block.greedy_ids = []
        block_list.get_block("cond_to_join").greedy_ids = ["PUSH [TAG]_0"]
        redirect, _ = removable_edge_blocks(block_list.blocks, {"then": 1, "join": 2, "cond_to_join": 3})
        assert redirect == {}

    def test_jumped_edge_block_is_retargeted_and_non_empty_one_kept(self):
        # cond jumps to the edge block: the tag pushed by cond is replaced by the one of join
        block_list = if_without_else()
        cond = block_list.get_block("cond")
        cond.set_jump_to("join")
        cond.set_falls_to("then")
        block_list.get_block("join").entries = ["cond", "then"]
        split_critical_edges_block_list(block_list)
        for block in block_list.blocks.values():
            block.greedy_ids = []
        edge_block = block_list.get_block("cond_to_join")
        edge_block.greedy_ids = ["PUSH [TAG]_0"]
        tags = {"then": 1, "join": 2, "cond_to_join": 3}
        redirect, aliases = removable_edge_blocks(block_list.blocks, tags)
        assert redirect == {"cond_to_join": "join"} and aliases == {"3": "2"}

        # An edge block that shuffles the stack is kept
        edge_block.greedy_ids = ["SWAP1", "PUSH [TAG]_0"]
        redirect, _ = removable_edge_blocks(block_list.blocks, tags)
        assert redirect == {}


def empty_block(block_id, greedy_ids=("PUSH [TAG]_0",), is_edge_block=False):
    """
    Unconditional block whose code is only the push of its jump tag
    """
    block = CFGBlock(block_id, [], "unconditional", dict())
    block.greedy_ids = list(greedy_ids)
    block.is_edge_block = is_edge_block
    return block


def conditional_block(block_id):
    block = CFGBlock(block_id, [], "conditional", dict())
    block.set_condition("0x01")
    block.greedy_ids = ["SWAP1"]
    return block


def terminal_block(block_id):
    block = CFGBlock(block_id, [CFGInstruction("stop", [], [])], "terminal", dict())
    block.greedy_ids = ["SWAP1"]
    return block


class TestThreadEmptyBlocks:

    def test_two_falls_into_the_same_block_through_a_chain(self, monkeypatch):
        # Shape of storage_array_ref's find: Block0 falls -> E0 -> Block2 and Block1 falls -> E1 -> Block4 (empty)
        # -> Block2. E0 (depth 1) is granted; E1 (depth 2) also reaches Block2, already fallen into, so it is kept
        monkeypatch.setattr("global_params.constants.THREAD_EMPTY_BLOCKS", True)
        blocks = [conditional_block("Block0"), conditional_block("Block1"),
                  empty_block("E0", is_edge_block=True), empty_block("E1", is_edge_block=True),
                  empty_block("Block4"), terminal_block("Block2"), terminal_block("Block3")]
        block_list = build_block_list(blocks, [("Block0", "Block1", "jumps_to"), ("Block0", "E0", "falls_to"),
                                               ("E0", "Block2", "jumps_to"), ("Block1", "Block3", "jumps_to"),
                                               ("Block1", "E1", "falls_to"), ("E1", "Block4", "jumps_to"),
                                               ("Block4", "Block2", "jumps_to")])
        tags = {"Block1": 1, "Block2": 2, "Block3": 3, "Block4": 4}
        redirect, aliases = removable_edge_blocks(block_list.blocks, tags)
        assert redirect == {"E0": "Block2", "Block4": "Block2"} and aliases == {"4": "2"}

    def test_fall_closest_to_the_target_is_granted_first(self, monkeypatch):
        # P1 falls -> F1 -> F2 -> T and P2 falls -> F2. Granting P1 first (F1 comes first) would deny P2, keeping F2,
        # and P1 would then reach F2, already fallen into by P2: nothing would be skipped. F2 is closer to T
        monkeypatch.setattr("global_params.constants.THREAD_EMPTY_BLOCKS", True)
        blocks = [conditional_block("P1"), empty_block("F1", is_edge_block=True), conditional_block("P2"),
                  empty_block("F2"), terminal_block("T"), terminal_block("X")]
        block_list = build_block_list(blocks, [("P1", "P2", "jumps_to"), ("P1", "F1", "falls_to"),
                                               ("F1", "F2", "jumps_to"), ("P2", "X", "jumps_to"),
                                               ("P2", "F2", "falls_to"), ("F2", "T", "jumps_to")])
        tags = {"P2": 1, "F2": 2, "T": 3, "X": 4}
        redirect, _ = removable_edge_blocks(block_list.blocks, tags)
        assert redirect == {"F2": "T"}

    def test_cycle_of_empty_blocks_keeps_one_block(self, monkeypatch):
        monkeypatch.setattr("global_params.constants.THREAD_EMPTY_BLOCKS", True)
        blocks = [conditional_block("S"), empty_block("A"), empty_block("B"), terminal_block("T")]
        block_list = build_block_list(blocks, [("S", "A", "jumps_to"), ("S", "T", "falls_to"),
                                               ("A", "B", "jumps_to"), ("B", "A", "jumps_to")])
        redirect, aliases = removable_edge_blocks(block_list.blocks, {"A": 1, "B": 2})
        assert redirect == {"B": "A"} and aliases == {"2": "1"}

    def test_tagged_block_leading_to_an_untagged_one_is_kept(self, monkeypatch):
        monkeypatch.setattr("global_params.constants.THREAD_EMPTY_BLOCKS", True)
        blocks = [conditional_block("S"), empty_block("A"), empty_block("B"), terminal_block("T"),
                  terminal_block("U")]
        block_list = build_block_list(blocks, [("S", "A", "jumps_to"), ("S", "U", "falls_to"),
                                               ("A", "B", "jumps_to"), ("B", "T", "jumps_to")])
        # B leads to T, which has no tag: B is kept and A leads to it
        redirect, aliases = removable_edge_blocks(block_list.blocks, {"A": 1, "B": 2})
        assert redirect == {"A": "B"} and aliases == {"1": "2"}

    def test_loop_back_edge_through_empty_blocks_is_kept(self, monkeypatch):
        # Shape of MegaSale's Strings.toString loop: L (the loop with its exit test) falls -> E1 (empty) -> E2 (empty)
        # -> L. Skipping both would make L fall into itself: E1 is kept, and E2 can still be skipped
        monkeypatch.setattr("global_params.constants.THREAD_EMPTY_BLOCKS", True)
        blocks = [conditional_block("S"), conditional_block("L"), empty_block("E1"), empty_block("E2"),
                  terminal_block("X")]
        # Nobody falls into L (as in MegaSale, both of its predecessors jump to it)
        block_list = build_block_list(blocks, [("S", "L", "jumps_to"), ("S", "X", "falls_to"),
                                               ("L", "X", "jumps_to"), ("L", "E1", "falls_to"),
                                               ("E1", "E2", "jumps_to"), ("E2", "L", "jumps_to")])
        tags = {"L": 1, "E2": 2, "X": 3}
        redirect, aliases = removable_edge_blocks(block_list.blocks, tags)
        assert "E1" not in redirect and redirect.get("E2", "L") == "L"

    def test_two_blocks_falling_into_each_other(self, monkeypatch):
        # A falls -> E1 -> B and B falls -> E2 -> A: granting both would be a cycle of falls. The second one is denied
        # because its faller is already fallen into (the rule that excludes every cycle longer than a self-fall)
        monkeypatch.setattr("global_params.constants.THREAD_EMPTY_BLOCKS", True)
        blocks = [conditional_block("S"), conditional_block("A"), conditional_block("B"), empty_block("E1"),
                  empty_block("E2"), terminal_block("X")]
        block_list = build_block_list(blocks, [("S", "A", "jumps_to"), ("S", "X", "falls_to"),
                                               ("A", "X", "jumps_to"), ("A", "E1", "falls_to"),
                                               ("E1", "B", "jumps_to"), ("B", "X", "jumps_to"),
                                               ("B", "E2", "falls_to"), ("E2", "A", "jumps_to")])
        tags = {"A": 1, "B": 2, "X": 3}
        redirect, _ = removable_edge_blocks(block_list.blocks, tags)
        assert ("E1" in redirect) != ("E2" in redirect)
