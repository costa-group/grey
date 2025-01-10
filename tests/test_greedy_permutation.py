import glob

import pytest
from typing import Dict
from parser.cfg_block import CFGBlock
from parser.cfg_instruction import build_instr_spec, build_verbatim_spec, build_push_spec, CFGInstruction
from greedy.greedy_new_version import greedy_from_file, STACK_DEPTH
from analysis.greedy_validation import check_execution_from_ids


class TestGreedyPermutation:

    def test_swap_element17(self):
        sfs, seq, outcome = greedy_from_file("greedy_permutation_files/swap_element17.json")
        print("LEN", len(seq))
        assert check_execution_from_ids(sfs, seq), "Failing SWAP17 tests"
