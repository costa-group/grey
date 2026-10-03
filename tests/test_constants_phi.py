"""
Tests for the propagation of constants (minimizing_constants_insertion): the arguments of the phi-functions must use
the variables introduced in the predecessor they come from (or in its dominators)
"""
import networkx as nx

from parser.cfg_block import CFGBlock
from parser.cfg_block_list import CFGBlockList
from parser.cfg_instruction import CFGInstruction
from cfg_methods.minimizing_constants_insertion import insert_variables_for_constants_block_list, \
    insert_constants_block_list

# Large enough to be propagated with two uses (see decide_if_propagated)
BIG = "0x010000000000000000"


def build_block_list(blocks, edges):
    """
    The first block is the start one. Edges are (source, target, "jumps_to" | "falls_to")
    """
    block_list = CFGBlockList("f")
    for i, block in enumerate(blocks):
        block_list.add_block(block, is_start_block=(i == 0))
    for u, v, kind in edges:
        block_list.blocks[v].add_comes_from(u)
        if kind == "jumps_to":
            block_list.blocks[u].set_jump_to(v)
        else:
            block_list.blocks[u].set_falls_to(v)
    return block_list


def propagate(block_list):
    constants_per_block, total_uses = insert_variables_for_constants_block_list(block_list)
    insert_constants_block_list(block_list, constants_per_block, total_uses)


def defined_in(block):
    return {out_arg for instruction in block.get_instructions() for out_arg in instruction.get_out_args()}


def assert_phi_arguments_defined(block_list):
    """
    Every variable used as a phi argument is defined in the corresponding predecessor or in one of its dominators
    """
    immediate_dominators = nx.immediate_dominators(block_list.to_graph(), block_list.start_block)
    for block in block_list.blocks.values():
        for phi in block.phi_instructions():
            for argument, predecessor in zip(phi.get_in_args(), block.entries):
                if argument.startswith("0x"):
                    continue
                dominator, available = predecessor, set()
                while True:
                    available |= defined_in(block_list.get_block(dominator))
                    if immediate_dominators[dominator] == dominator:
                        break
                    dominator = immediate_dominators[dominator]
                assert argument in available, f"{argument} is not defined at the end of {predecessor}"


def push_of(block, constant):
    return [instruction.get_out_args()[0] for instruction in block.get_instructions()
            if instruction.get_op_name() == "push" and instruction.literal_args == [constant]]


def test_if_without_else_uses_the_predecessor_constant():
    # B0 -> B1 -> B2 and B0 -> B2. B2: v = phi(0x05 from B0, BIG from B1) and BIG is used again in B2. B2 does not
    # dominate B1, so the phi argument must be the variable pushed in B1, not the one pushed in B2
    b0 = CFGBlock("B0", [CFGInstruction("calldataload", ["0x00"], ["x"]),
                         CFGInstruction("JUMPI", [], [])], "conditional", dict())
    b1 = CFGBlock("B1", [CFGInstruction("mstore", ["x", "0x00"], []), CFGInstruction("JUMP", [], [])],
                  "unconditional", dict())
    b2 = CFGBlock("B2", [CFGInstruction("PhiFunction", ["0x05", BIG], ["v"]),
                         CFGInstruction("lt", [BIG, "v"], ["w"]),
                         CFGInstruction("sstore", ["w", "0x00"], [])], "terminal", dict())
    b2.entries = ["B0", "B1"]
    block_list = build_block_list([b0, b1, b2], [("B0", "B1", "jumps_to"), ("B0", "B2", "falls_to"),
                                                 ("B1", "B2", "jumps_to")])
    propagate(block_list)

    phi = b2.phi_instructions()[0]
    assert phi.get_in_args()[0] == "0x05"
    assert push_of(b1, BIG) == [phi.get_in_args()[1]]
    assert push_of(b2, BIG) != push_of(b1, BIG)
    assert_phi_arguments_defined(block_list)


def test_loop_back_edge_uses_the_header_constant():
    # B0 -> B1 (header) -> B2 -> B1, B1 -> B3. B1: v = phi(0x00 from B0, BIG from B2) and BIG is used in B1, which
    # dominates B2: the back edge uses the header's variable
    b0 = CFGBlock("B0", [CFGInstruction("JUMP", [], [])], "unconditional", dict())
    b1 = CFGBlock("B1", [CFGInstruction("PhiFunction", ["0x00", BIG], ["v"]),
                         CFGInstruction("lt", [BIG, "v"], ["w"]),
                         CFGInstruction("JUMPI", [], [])], "conditional", dict())
    b1.entries = ["B0", "B2"]
    b2 = CFGBlock("B2", [CFGInstruction("sstore", ["v", "0x00"], []), CFGInstruction("JUMP", [], [])],
                  "unconditional", dict())
    b3 = CFGBlock("B3", [CFGInstruction("stop", [], [])], "terminal", dict())
    block_list = build_block_list([b0, b1, b2, b3], [("B0", "B1", "jumps_to"), ("B1", "B2", "jumps_to"),
                                                     ("B1", "B3", "falls_to"), ("B2", "B1", "jumps_to")])
    propagate(block_list)

    phi = b1.phi_instructions()[0]
    assert phi.get_in_args() == ["0x00"] + push_of(b1, BIG)
    assert push_of(b2, BIG) == []
    assert_phi_arguments_defined(block_list)
