"""
When the head of the store order is a forced read (e.g. a RETURNDATASIZE needed after the next call), the greedy
computes a final value by executing the pending store operations in a batch (case 1 of SMSgreedy.compute). The dead
values left on top by those operations (e.g. the unused result of a call) must be popped as in the main loop:
otherwise they stay until the end of the block and push other values out of reach
"""
from parser.parser import parse_instruction
from parser.cfg_block import CFGBlock
from greedy.greedy_previous_param import greedy_standalone
from analysis.greedy_validation import check_execution_from_ids


def instruction(op, yul_args, out_args=()):
    """
    Builds a CFGInstruction from its arguments in Yul order (the JSON of the yul CFG lists them reversed)
    """
    return parse_instruction({"op": op, "in": list(yul_args)[::-1], "out": list(out_args)}, {})


def identity_copy(offset, out):
    # staticcall(gas, 4, offset, n, 0x80, n): copy with the identity precompile, as Solady does
    return instruction("staticcall", ["vg", "0x04", offset, "vn", "0x80", "vn"], [out])


def test_unused_call_results_are_popped_in_the_batch():
    # Shape of Solady's _checkOnERC1155BatchReceived: each returndatasize is used after the next call
    instructions = [identity_copy("va", "vs1"), instruction("pop", ["vs1"]),
                    instruction("returndatasize", [], ["vr1"]),
                    identity_copy("vb", "vs2"), instruction("pop", ["vs2"]),
                    instruction("returndatasize", [], ["vr2"]),
                    instruction("add", ["vr1", "vr2"], ["vt"]), instruction("mstore", ["0xa0", "vt"]),
                    instruction("call", ["vg", "vto", "0x00", "0x80", "vr1", "0x00", "0x20"], ["vc"]),
                    instruction("iszero", ["vc"], ["vz"])]
    spec = CFGBlock("Block", instructions, "terminal", {}).build_spec(["vg", "va", "vb", "vn", "vto"], ["vz"])
    _, _, ids = greedy_standalone(spec, False, 16)
    check_execution_from_ids(spec, ids, False)

    following_calls = [ids[position + 1] for position, instr_id in enumerate(ids)
                       if instr_id.startswith("STATICCALL")]
    assert following_calls == ["POP", "POP"], ids
