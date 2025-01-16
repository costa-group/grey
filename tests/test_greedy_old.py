import glob

import pytest
from typing import Dict
from parser.cfg_block import CFGBlock
from parser.cfg_instruction import build_instr_spec, build_verbatim_spec, build_push_spec, CFGInstruction
from greedy.greedy import SMSgreedy, greedy_from_file
import json


class TestGreedyOld:

    def test_array_allocation(self):
        _, _, error = greedy_from_file("greedy_old/array_allocation_size_t_bytes_memory_ptr_Block2_split_0.json")
        assert error != "error", "Falla test"
