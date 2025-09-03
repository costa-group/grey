import pytest
from greedy.greedy_new_version import greedy_from_file
from analysis.greedy_validation import check_execution_from_ids

class TestGreedyNewVersion:

    def test_no_fixed_elements(self):
        """
        If an element has no elements to be fixed, we
        must explicitly state that self.fixed_elements is
        equal to -1 (as they are not needed).
        
        Fixed in commit cb2c793
        """
        sfs, greedy_info = greedy_from_file("greedy_new_version/no_fixed_elements.json")
        seq = greedy_info.greedy_ids
        assert check_execution_from_ids(sfs, seq), "Incorrect solution for no fixed elements test"

    def test_duplication_cheap_instructions(self):
        """
        We only mark for duplication those instructions that
        must be duplicated. For cheap instructions, we perform no
        changes.

        Fixed in commit f32c28c
        """
        sfs, greedy_info = greedy_from_file("greedy_new_version/duplication_cheap_instructions.json")
        seq = greedy_info.greedy_ids
        assert check_execution_from_ids(sfs, seq), "Incorrect solution for duplication cheap instructions"

    def test_stack_too_deep_select_candidates(self):
        """
        When we have a stack too deep case (a variable must be
        placed in an unreachable place), we just select a candidate
        based in other factors.

        Fixed in commit e754178
        """
        sfs, greedy_info = greedy_from_file("greedy_new_version/stack_too_deep_select_candidates.json")
        seq = greedy_info.greedy_ids
        assert check_execution_from_ids(sfs, seq), "Incorrect solution for stack too deep select candidates"
