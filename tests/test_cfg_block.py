import glob

import pytest
from typing import Dict
from parser.parser import parse_instruction
from parser.cfg_block import CFGBlock, CFGInstruction
from parser.cfg_instruction import build_instr_spec, build_verbatim_spec, build_push_spec, CFGInstruction
from greedy.greedy_old import SMSgreedy, greedy_from_file
import json


class TestCFGBlock:

    def test_keccak_array_position(self):
        """
        Problem: the dict "map_position" in build spec introduced a dict in the memory_dependencies when a KECCAK256
        was introduced more than once.

        Solution: assign ["id"]
        """
        instructions = [{"in": [], "out": ["c280"], "op": "push", "builtinArgs": ["0xff"]},
                        {"in": [], "out": ["c279"], "op": "push",
                         "builtinArgs": ["0xffffffffffffffffffffffffffffffffffffffff"]},
                        {"in": [], "out": ["c278"], "op": "push", "builtinArgs": ["0x40"]},
                        {"in": [], "out": ["c277"], "op": "push", "builtinArgs": ["0x97"]},
                        {"in": [], "out": ["c276"], "op": "push", "builtinArgs": ["0x20"]},
                        {"in": [], "out": ["c275"], "op": "push", "builtinArgs": ["0x00"]},
                        {"in": ["c275", "v84_f313_1_f482_1"], "out": [], "op": "mstore"},
                        {"in": ["c276", "c277"], "out": [], "op": "mstore"},
                        {"in": ["c275", "c278"], "out": ["v2496_f312_3_f521_0"], "op": "keccak256"},
                        {"in": ["v2496_f312_3_f521_0", "c275"], "out": ["v1972_f521_0"], "op": "add"},
                        {"in": ["v62_f428_3_f482_1", "c279"], "out": ["v994_f79_2_f253_1_f359_0_f431_4_f486_2_f521_0"],
                         "op": "and"},
                        {"in": ["v994_f79_2_f253_1_f359_0_f431_4_f486_2_f521_0", "c279"],
                         "out": ["v994_f79_3_f253_1_f359_0_f431_4_f486_2_f521_0"], "op": "and"},
                        {"in": ["c275", "v994_f79_3_f253_1_f359_0_f431_4_f486_2_f521_0"], "out": [], "op": "mstore"},
                        {"in": ["c276", "v1972_f521_0"], "out": [], "op": "mstore"},
                        {"in": ["c275", "c278"], "out": ["v2488_f486_2_f521_0"], "op": "keccak256"},
                        {"in": ["v2488_f486_2_f521_0"], "out": ["v2638_f379_1_f521_0"], "op": "sload"},
                        {"in": ["c275", "v2638_f379_1_f521_0"], "out": ["v2770_f81_2_f379_1_f521_0"], "op": "shr"},
                        {"in": ["v2770_f81_2_f379_1_f521_0", "c280"], "out": ["v950_f126_0_f379_1_f521_0"],
                         "op": "and"},
                        {"in": [], "out": ["v1382"], "op": "allocate_unbounded"}]
        instructions_cfg = [parse_instruction(instruction) for instruction in instructions]
        block = CFGBlock("validator_revert_t_address_Block2_copy_3_copy_1", instructions_cfg, "terminal", {})
        input_stack = ['v62_f428_3_f482_1', 'v84_f313_1_f482_1']
        output_stack = ['v1382', 'v950_f126_0_f379_1_f521_0']
        sfs = block.build_spec(input_stack ,output_stack)

        assert all(isinstance(term, str) for dep in sfs["memory_dependences"] for term in dep), \
            "Falla test keccak_array_position"
