import glob

import pytest
from typing import Dict
from parser.cfg_block import CFGBlock
from parser.cfg_instruction import build_instr_spec, build_verbatim_spec, build_push_spec, CFGInstruction
from greedy.greedy import SMSgreedy, greedy_from_file
import json


class TestGreedyOld:

    def test_array_allocation(self):
        """
        If the stack already contains all the copies needed and is a subterm of current computation, it tries
        to reuse it using a swap instruction. However, if one of the copies is already part of a computation,
        it tries to access one copy that is not part of it. In this case, there are no other copies and it fails
        when trying to retrieve the position (ask Albert)
        
        FIX: adding condition "pos >= self._dup_stack_ini or o in stack[self._dup_stack_ini:])" to ensure
        we only try to swap it there is an available element
        """
        sfs, greedy_info = greedy_from_file("greedy_old/swap_only_if_available.json")
        assert greedy_info.outcome != "error", "Falla test"
