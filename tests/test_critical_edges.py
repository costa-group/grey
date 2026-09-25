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
