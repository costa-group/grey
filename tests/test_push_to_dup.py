"""
push_to_dup replaces the PUSHes of values already in the stack by DUPs. It runs once on the final ids of every block
(cfg_push_to_dup), after the reparation, so it must understand the code emitted by the reparation
"""
from parser.parser import parse_instruction
from parser.cfg_block import CFGBlock
from parser.cfg_block_list import CFGBlockList
from greedy.ids_from_spec import push_to_dup, cfg_block_list_push_to_dup

# Spec PUSH of 0xa0 (as in the SFS: "value" is a list with the integer)
INSTR_MAP = {"PUSH_0": {"id": "PUSH_0", "disasm": "PUSH", "value": [160], "push": True, "size": 2,
                        "inpt_sk": [], "outpt_sk": ["s0"]},
             "PUSH0_0": {"id": "PUSH0_0", "disasm": "PUSH0", "value": [0], "push": True, "size": 1,
                         "inpt_sk": [], "outpt_sk": ["s1"]},
             "ADD_0": {"id": "ADD_0", "disasm": "ADD", "push": False, "size": 1,
                       "inpt_sk": ["vx", "vy"], "outpt_sk": ["vz"]}}


def test_spec_push_after_a_slot_address_becomes_dup():
    # "PUSH a0" is the address of a memory slot emitted by the reparation; the loaded value is unknown
    ids = ["PUSH a0", "MLOAD", "PUSH_0"]
    assert push_to_dup(ids, [], INSTR_MAP) == ["PUSH a0", "MLOAD", "PUSH_0"]
    ids = ["PUSH a0", "DUP1", "MLOAD", "PUSH_0"]
    assert push_to_dup(ids, [], INSTR_MAP) == ["PUSH a0", "DUP1", "MLOAD", "DUP2"]


def test_slot_address_after_a_spec_push_becomes_dup():
    ids = ["PUSH_0", "PUSH a0", "MLOAD"]
    assert push_to_dup(ids, [], INSTR_MAP) == ["PUSH_0", "DUP1", "MLOAD"]


def test_phi_copy_constant_becomes_dup():
    ids = ["PUSH-CONSTANT 0xa0", "PUSH-CONSTANT 0xa0"]
    assert push_to_dup(ids, [], INSTR_MAP) == ["PUSH-CONSTANT 0xa0", "DUP1"]


def test_stores_of_the_reparation_keep_the_depths():
    # VSET: the stored value and the address are consumed, so the 0xa0 below is at depth 1 afterwards
    ids = ["PUSH_0", "DUP2", "PUSH 80", "MSTORE", "POP", "ADD_0", "PUSH_0"]
    assert push_to_dup(ids, ["vx", "vy", "vw"], INSTR_MAP) == ["PUSH_0", "DUP2", "PUSH 80", "MSTORE", "POP", "ADD_0",
                                                              "PUSH_0"]
    ids = ["PUSH_0", "DUP2", "PUSH 80", "MSTORE", "PUSH_0"]
    assert push_to_dup(ids, ["vx"], INSTR_MAP) == ["PUSH_0", "DUP2", "PUSH 80", "MSTORE", "DUP1"]


def test_push0_is_never_replaced():
    ids = ["PUSH0_0", "PUSH0_0", "PUSH-CONSTANT 0x00"]
    assert push_to_dup(ids, [], INSTR_MAP) == ids


def test_unknown_ids_stop_the_simulation():
    ids = ["PUSH_0", "VGET(vx)", "PUSH_0"]
    assert push_to_dup(ids, [], INSTR_MAP) == ids


def instruction(op, yul_args, out_args=()):
    return parse_instruction({"op": op, "in": list(yul_args)[::-1], "out": list(out_args)}, {})


def test_block_list_pass_uses_the_final_ids():
    # Final ids of a block rebuilt by the reparation (a VGET in the middle): the 0xa0 pushed again becomes a DUP
    block = CFGBlock("Block", [instruction("mstore", ["0xa0", "vx"]), instruction("mload", ["0xa0"], ["vy"])],
                     "terminal", {})
    block.spec = block.build_spec(["vx"], ["vy"])
    block_list = CFGBlockList("list")
    block_list.add_block(block, is_start_block=True)
    block.greedy_ids = ["PUSH_0", "PUSH 80", "MLOAD", "SWAP1", "PUSH_0"]
    cfg_block_list_push_to_dup(block_list)
    assert block.greedy_ids == ["PUSH_0", "PUSH 80", "MLOAD", "SWAP1", "DUP1"]
