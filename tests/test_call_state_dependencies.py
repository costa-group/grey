"""
Reads of the state that calls and creates may change (SELFBALANCE, BALANCE, RETURNDATASIZE) must stay between the
same calls/creates: they are ordered like SLOADs, and the greedy cannot recompute them (a recomputed SELFBALANCE after
a call that transferred value reads another balance)
"""
from typing import List

import pytest

from parser.parser import parse_instruction
from parser.cfg_block import CFGBlock
from analysis.instruction_dependencies import compute_call_state_dependences
from analysis.greedy_validation import check_execution_from_ids
from greedy.greedy_previous_param import greedy_standalone

# Variable names start with "v": the spec names its constants "s<i>"
READS = {"SELFBALANCE", "BALANCE", "RETURNDATASIZE"}
WRITES = {"CALL", "STATICCALL", "CREATE"}


def instruction(op: str, yul_args: List[str], out_args: List[str] = None):
    """
    Builds a CFGInstruction from its arguments in Yul order (the JSON of the yul CFG lists them reversed)
    """
    return parse_instruction({"op": op, "in": yul_args[::-1], "out": out_args or []}, {})


def call(value: str, out: str, in_offset: str = "0x00", in_size: str = "0x00"):
    return instruction("call", ["vg", "va", value, in_offset, in_size, "0x00", "0x00"], [out])


def selfbalance(out: str):
    return instruction("selfbalance", [], [out])


def test_balance_reads_are_ordered_with_value_transfers_only():
    instructions = [instruction("staticcall", ["vg", "va", "0x00", "0x00", "0x00", "0x00"], ["vs"]),
                    selfbalance("vb"),
                    call("0x00", "vc")]
    assert compute_call_state_dependences(instructions) == [[1, 2]]


def test_returndatasize_is_ordered_with_every_call():
    instructions = [instruction("staticcall", ["vg", "va", "0x00", "0x00", "0x00", "0x00"], ["vs"]),
                    instruction("returndatasize", [], ["vr"]),
                    call("0x00", "vc")]
    assert compute_call_state_dependences(instructions) == [[0, 1], [1, 2]]


# (instructions, initial stack, final stack): blocks with balance reads around calls
SHAPES = {
    # StargatePoolUSDC's withdrawPlannerFee: the balance is sent and used after the call
    "read_sent_and_live_out": ([selfbalance("vb"), call("vb", "vc")], ["vg", "va"], ["vc", "vb"]),
    "read_used_after_call": ([selfbalance("vb"), call("vb", "vc"), instruction("mstore", ["0x80", "vb"])],
                             ["vg", "va"], ["vc"]),
    "read_after_call": ([instruction("mstore", ["0x80", "vx"]), call("0x00", "vc", "0x80", "0x20"), selfbalance("vb"),
                         instruction("add", ["vb", "0x01"], ["vy"])], ["vg", "va", "vx"], ["vy", "vc"]),
    "two_calls": ([selfbalance("vb1"), call("vb1", "vc1"), selfbalance("vb2"), call("vb2", "vc2")],
                  ["vg", "va"], ["vc2", "vc1", "vb1", "vb2"]),
    "reads_used_at_the_end": ([selfbalance("vb1"), call("0x01", "vc1"), selfbalance("vb2"), call("0x01", "vc2"),
                               instruction("sub", ["vb1", "vb2"], ["vd"])], ["vg", "va"], ["vd", "vc1", "vc2"]),
    "reads_stored_around_calls": ([selfbalance("vb1"), call("0x01", "vc1"), selfbalance("vb2"),
                                   instruction("mstore", ["0x80", "vb1"]), call("0x01", "vc2", "0x80", "0x20"),
                                   instruction("mstore", ["0xa0", "vb2"]), instruction("mstore", ["0xc0", "vb1"])],
                                  ["vg", "va"], ["vc1", "vc2"]),
    "read_after_call_live_out": ([call("0x01", "vc1"), selfbalance("vb2")], ["vg", "va"], ["vc1", "vb2"]),
    "read_after_call_stored": ([call("0x01", "vc1"), selfbalance("vb2"), instruction("mstore", ["0x80", "vb2"])],
                               ["vg", "va"], ["vc1"]),
}


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_balance_reads_stay_between_the_same_calls(shape):
    instructions, initial_stack, final_stack = SHAPES[shape]
    spec = CFGBlock("Block", instructions, "terminal", {}).build_spec(list(initial_stack), list(final_stack))
    _, _, ids = greedy_standalone(spec, False, 16)
    check_execution_from_ids(spec, ids, False)

    # Ids of the reads and writes in program order (the spec numbers each opcode in order)
    program = []
    for ins in instructions:
        opcode = ins.get_op_name().upper()
        if opcode in READS | WRITES:
            program.append(f"{opcode}_{sum(1 for other in program if other.startswith(opcode + '_'))}")

    def writes_before(sequence, position):
        return sum(1 for instr_id in sequence[:position] if instr_id.split("_")[0] in WRITES)

    for read in [instr_id for instr_id in program if instr_id.split("_")[0] in READS]:
        expected_writes = writes_before(program, program.index(read))
        executions = [position for position, instr_id in enumerate(ids) if instr_id == read]
        assert executions, f"{read} is not computed"
        assert all(writes_before(ids, position) == expected_writes for position in executions), \
            f"{read} is computed after another number of calls: {ids}"
