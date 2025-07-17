"""
Tests for tree scan method
"""

import pytest
import networkx as nx
from typing import List
from parser.cfg_block_list import CFGBlockList, CFGBlock
from graphs.cfg import compute_loop_nesting_forest_graph
from graphs.algorithms import compute_dominance_tree
from parser.cfg_instruction import CFGInstruction
from liveness.tree_scan import TreeScanFirstPass, ColourAssignment


def block_with_stacks(block_name: str, greedy_ids: List[str],
                      initial_stack: List[str], final_stack: List[str], instructions: List[str] = None):
    """
    Construct blocks with all the information needed for the reconstruction.
    The initial and final stacks do not need to match the instructions in block_instrs
    """
    if not instructions:
        instructions = []

    block = CFGBlock(block_name, instructions, "", {})
    block._reachable_in = set(initial_stack[:16])
    block._reachable_out = set(final_stack[:16])
    # We declare simply instructions for link the variable to the id
    block._id2var = {f"INSTR_{i}": stack_value for i, stack_value in
                     enumerate(set(final_stack).difference(final_stack))}

    block.greedy_ids = greedy_ids
    return block


def build_stack(n: int):
    return [f"v{i}" for i in reversed(range(n + 1))]


def setup_cfg_example():
    block_0 = block_with_stacks("block_0", ["Op2", "...", "Op7", "PUSH [tag] 1", "JUMP"],
                                build_stack(1), build_stack(7))

    block_1 = block_with_stacks("block_1", ["Op8", "...", "Op17", "DUP1", "PUSH0", "PUSH [tag] 2", "JUMP"],
                                build_stack(7), [0, "v17"] + build_stack(17))

    block_0.set_falls_to(block_1.block_id)

    block_2 = block_with_stacks("block_2", ["POP", "PUSH [tag] 3", "JUMP"],
                                ["bot", "v22"] + build_stack(17), ["v22"] + build_stack(17))

    block_1.set_falls_to(block_2.block_id)

    block_3 = block_with_stacks("block_3", ["POP", "PUSH [tag] 3", "JUMP"],
                                ["bot", "v22"] + build_stack(17), ["v22"] + build_stack(17))

    block_2.set_falls_to(block_3.block_id)

    block_4 = block_with_stacks("block_4", ["GET(v0)", "PUSH1 0x01", "ADD", "PUSH [tag] 6", "JUMP"],
                                ["v22", "v17"] + build_stack(17), ["v18", "v22"] + build_stack(17))

    block_3.set_jump_to(block_4.block_id)

    block_5 = block_with_stacks("block_5", ["GET(v0)", "PUSH1 0x02", "ADD", "PUSH [tag] 6", "JUMP"],
                                ["v22", "v17"] + build_stack(17), ["v19", "v22"] + build_stack(17))
    block_3.set_falls_to(block_5.block_id)

    block_6 = block_with_stacks("block_6", ["SWAP1", "PUSH1 0x10", "DUP3", "LT", "PUSH [tag] 2", "JUMPI"],
                                ["v20", "v22", "v17"] + build_stack(17), ["v22", "v20"] + build_stack(17))
    block_4.set_jump_to(block_6.block_id)
    block_5.set_jump_to(block_6.block_id)
    block_6.set_jump_to(block_2.block_id)

    block_7 = block_with_stacks("block_7", ["GET(v3)", "SSTORE", "POP", "SWAP1", "SET(v16)", "GET(v16)", "SWAP1"],
                                ["v22", "bot"] + build_stack(17), ["v0"] + build_stack(16)[:-1] + ["v17"])

    block_6.set_falls_to(block_7.block_id)

    block_list = CFGBlockList("example")
    block_list.blocks = {block.block_id: block for block in
                         [block_0, block_1, block_2, block_3,
                          block_4, block_5, block_6, block_7]}
    block_list.start_block = block_0.block_id
    return block_list


class TestGreedyNewVersion:

    def test_first_phase(self):
        example_block_list = setup_cfg_example()
        cfg_graph = example_block_list.to_graph()
        dominance_tree = compute_dominance_tree(cfg_graph, example_block_list.start_block)
        loop_nesting_forest = compute_loop_nesting_forest_graph(cfg_graph, dominance_tree)
        first_pass_object = TreeScanFirstPass(example_block_list, loop_nesting_forest)
        detect_last_accessible = first_pass_object.insert_instructions()

        second_copy = setup_cfg_example()

        # First check the modifications in the blocks (can be in either order)
        assert example_block_list.get_block("block_1").greedy_ids[:2] in [["DUP_SET(v3)", "DUP_SET(v0)"], ["DUP_SET(v0)",
                                                                                                           "DUP_SET(v3)"]]

        assert example_block_list.get_block("block_1").greedy_ids[2:] == second_copy.get_block("block_1").greedy_ids

        for block_id in example_block_list.blocks:
            if block_id != "block_1":
                modified_ids = example_block_list.get_block(block_id).greedy_ids
                original_ids = second_copy.get_block(block_id).greedy_ids
                assert modified_ids == original_ids, f"{block_id} has modified the ids.\n" \
                                                     f"Original ids: {original_ids}\n" \
                                                     f"Modified ids: {modified_ids}"

        # Then, we just traverse the last accessible
        assert detect_last_accessible == {"block_4": {"v0"}, "block_7": {"v3", "v16"}}

    def test_second_phase(self):
        example_block_list = setup_cfg_example()
        cfg_graph = example_block_list.to_graph()
        dominance_tree = compute_dominance_tree(cfg_graph, example_block_list.start_block)

        # Modify the example introducing the DUP_SET instructions
        last_accessible = {"block_4": {"v0"}, "block_7": {"v3", "v16"}}

        block_1 = example_block_list.get_block("block_1")
        block_1._greedy_ids.insert(0, "DUP_SET(v0)")
        block_1._greedy_ids.insert(0, "DUP_SET(v3)")

        colour_assignment = ColourAssignment(example_block_list, dominance_tree, last_accessible)
        colour_assignment.tree_scan_with_last_uses()