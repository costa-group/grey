import glob

import pytest
from typing import Dict
from parser.cfg_block import CFGBlock
from parser.cfg_instruction import build_instr_spec, build_verbatim_spec, build_push_spec, CFGInstruction
from greedy.greedy_new_version import SMSgreedy, greedy_from_file
import json


class TestGreedyPermutation:

    def test_deepest_position_op(self):
        with open("sfs/deepest_position_op_simple.json", 'r') as f:
            sms = json.load(f)
        greedy_object = SMSgreedy(sms)
        instr = greedy_object._id2instr["ADD_0"]
        initial_state = greedy_object._initialize_initial_state()
        deepest_position = greedy_object._deepest_position_op(instr, initial_state)
        assert initial_state.stack[deepest_position] == "s(17)", "Expected value: s(17)"

    def test_missing_element_list(self):
        sfs, seq, outcome = greedy_from_file("sfs/missing_element_list.json")
        assert outcome != "error", "Error in test test_missing_element_list"

    def test_repeated_argument_tree_dataflow(self):
        """
        Fails because the tree dataflow was a DiGraph, and it had to be a MultiDiGraph because
        an element can have repeated arguments.

        Also, this is an example in which we could consume an element that is already computed because
        this value is also used as part of a subcomputation
        """
        sfs, seq, outcome = greedy_from_file("sfs/repeated_argument_tree_dataflow.json")
        assert outcome != "error", "Error in test json"

    def test_var_elem_reused_split(self):
        """
        It assumed there was an element that was not already placed in their position due because
        the method var_elem_can_be_reused returned -1 either if there were no elements to swap or the element to
        swap was to deep.

        Fix: split function var_elem_can_be_reused into another method position_to_swap. var_elem_can_be_reused just
        checks if an element can be used safely and position_to_swap returns in which position we can reuse an element.
        """
        sfs, seq, outcome = greedy_from_file("sfs/var_elem_reused_split.json")
        assert outcome != "error", "Error in test json"

    def test_fails_16_1(self):
        sfs, seq, outcome = greedy_from_file("sfs/fails_16_1.json")
        assert outcome != "error", "Error in test json"
