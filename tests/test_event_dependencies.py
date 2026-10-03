"""
Dependencies that keep the order of the logs (LOGx and the calls/creates that can emit them in their own frame), which
the memory dependences miss
"""
from typing import List, Tuple

from parser.parser import parse_instruction
from parser.cfg_block import CFGBlock
from analysis.instruction_dependencies import compute_event_dependences
from greedy.greedy_previous_param import greedy_standalone


def instruction(op: str, yul_args: List[str], out_args: List[str] = None):
    """
    Builds a CFGInstruction from its arguments in Yul order (the JSON of the yul CFG lists them reversed)
    """
    return parse_instruction({"op": op, "in": yul_args[::-1], "out": out_args or []}, {})


def block_spec(instructions, initial_stack: List[str], final_stack: List[str]):
    return CFGBlock("Block", instructions, "terminal", {}).build_spec(initial_stack, final_stack)


def call_args(in_offset: str, out_offset: str) -> List[str]:
    """
    Arguments of call(gas, address, value, in_offset, in_size, out_offset, out_size) on disjoint constant ranges
    """
    return ["g", "a", "0x00", in_offset, "0x20", out_offset, "0x20"]


def test_two_logs_on_disjoint_memory_are_ordered():
    # Both LOGs only read memory and their ranges do not overlap: no memory dependency orders them
    instructions = [instruction("log1", ["0x00", "0x20", "t"]), instruction("log1", ["0x40", "0x20", "u"])]
    assert compute_event_dependences(instructions) == [[0, 1]]

    spec = block_spec(instructions, ["t", "u"], [])
    assert ["LOG1_0", "LOG1_1"] in spec["memory_dependences"]
    assert ["LOG1_0", "LOG1_1"] in spec["dependencies"]

    _, _, ids = greedy_standalone(spec, False, 16)
    assert ids.index("LOG1_0") < ids.index("LOG1_1")


def test_log_and_call_on_disjoint_memory_are_ordered():
    # The callee can emit logs too
    instructions = [instruction("log0", ["0x00", "0x20"]),
                    instruction("call", call_args("0x40", "0x80"), ["s"]),
                    instruction("log0", ["0xc0", "0x20"])]
    assert compute_event_dependences(instructions) == [[0, 1], [1, 2]]

    spec = block_spec(instructions, ["g", "a"], ["s"])
    assert ["LOG0_0", "CALL_0"] in spec["memory_dependences"]
    assert ["CALL_0", "LOG0_1"] in spec["memory_dependences"]


def test_staticcall_is_not_an_event():
    # A static frame cannot emit logs, so it does not need to be ordered with them
    instructions = [instruction("log0", ["0x00", "0x20"]),
                    instruction("staticcall", ["g", "a", "0x40", "0x20", "0x80", "0x20"], ["s"]),
                    instruction("log0", ["0xc0", "0x20"])]
    assert compute_event_dependences(instructions) == [[0, 2]]

