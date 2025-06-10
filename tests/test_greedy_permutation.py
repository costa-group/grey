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
        assert check_execution_from_ids(sfs, seq), "Incorrect solution for SWAP17 tests"
        desired_ids = ['SET(s(0))', 'SET(s(1))', 'GET(s(0))', 'SWAP16', 'GET(s(1))', 'SWAP1']
        assert desired_ids == seq, "Not reaching desired solution in SWAP17 test"

    def test_swap_s2_s17(self):
        sfs, seq, outcome = greedy_from_file("greedy_permutation_files/swap_s2_s17.json")
        print("LEN", len(seq))
        assert check_execution_from_ids(sfs, seq), "Incorrect solution for swap(s2, s17) test"
        desired_ids = ['SET(s(0))', 'SWAP16', 'SWAP1', 'SWAP16', 'GET(s(0))']
        assert desired_ids == seq, "Not reaching desired solution in swap(s2, s17) test"

    def test_swap_s6_s17(self):
        sfs, seq, outcome = greedy_from_file("greedy_permutation_files/swap_s6_s17.json")
        print("LEN", len(seq))
        assert check_execution_from_ids(sfs, seq), "Incorrect solution for swap(s6, s17) test"
        desired_ids = ['SET(s(0))', 'SWAP16', 'SWAP5', 'SWAP16', 'GET(s(0))']
        assert desired_ids == seq, "Not reaching desired solution in swap(s2, s17) test"
