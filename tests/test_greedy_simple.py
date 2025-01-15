import glob

import pytest
from typing import Dict
from parser.cfg_block import CFGBlock
from parser.cfg_instruction import build_instr_spec, build_verbatim_spec, build_push_spec, CFGInstruction
from greedy.greedy_new_version import greedy_from_file, STACK_DEPTH

class TestCFGInstruction:

    def test_example1(self):
        sfs, seq, outcome = greedy_from_file("sfs/complex.json")
        print("")
        print("LEN", len(seq))
        assert True

    def test_infinite_loop(self):
        """
        Failed because not_solved could add negative index
        """
        sfs, seq, outcome = greedy_from_file("sfs/infinite_loop.json")
        print("")
        print("LEN", len(seq))
        assert True

    def test_fails(self):
        """
        Failed because not_solved could add negative indexis
        """
        sfs, seq, outcome = greedy_from_file("sfs/fails.json")
        print("")
        print("LEN", len(seq))
        assert True


    def test_push_tag_computation(self):
        # Simple example with PUSH [tag] that must be handled
        sfs, seq, outcome = greedy_from_file("sfs/simple_push_tag.json")
        assert outcome != "error", "Error in test test_push_tag_computation"
