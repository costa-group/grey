"""
Tests for the per-function calling convention (--call-convention args / orders)
"""
import subprocess
from pathlib import Path

import pandas as pd
import pytest

from parser.cfg_block import CFGBlock
from parser.cfg_block_list import CFGBlockList
from parser.cfg_instruction import CFGInstruction
from liveness.calling_convention import (FunctionConvention, argument_order, return_order, block_order, first_uses,
                                         definition_points, _matches)

REPO_ROOT = Path(__file__).resolve().parent.parent
SOLC = REPO_ROOT.joinpath("examples/solc-without-opt")
BASE64 = REPO_ROOT.joinpath("examples/test/semanticTests/externalContracts_base64/base64_standard_input.json")


def chain_block_list(instructions_per_block):
    """
    Block list with a chain of blocks B0 -> B1 -> ... with the given instructions
    """
    block_list = CFGBlockList("f")
    names = [f"B{i}" for i in range(len(instructions_per_block))]
    for i, (name, instructions) in enumerate(zip(names, instructions_per_block)):
        block = CFGBlock(name, instructions, "unconditional" if i + 1 < len(names) else "terminal", dict())
        block_list.add_block(block, is_start_block=(i == 0))
    for u, v in zip(names, names[1:]):
        block_list.blocks[u].set_jump_to(v)
        block_list.blocks[v].add_comes_from(u)
    return block_list


class TestArgumentOrder:

    def test_closest_use_first(self):
        # b is used in the entry block, a in the next one
        uses = {"b": (0, 1, 0), "a": (1, 0, 0)}
        assert argument_order(["a", "b"], {"a", "b"}, uses) == [1, 0]

    def test_first_use_within_the_block(self):
        uses = {"a": (0, 2, 0), "b": (0, 1, 1)}
        assert argument_order(["a", "b"], {"a", "b"}, uses) == [1, 0]

    def test_dead_arguments_on_top(self):
        uses = {"a": (0, 0, 0), "c": (1, 0, 0)}
        assert argument_order(["a", "b", "c"], {"a", "c"}, uses) == [1, 0, 2]

    def test_ties_keep_yul_order(self):
        uses = {"a": (1, 0, 0), "b": (1, 0, 0)}
        assert argument_order(["a", "b"], {"a", "b"}, uses) == [0, 1]


class TestReturnOrder:

    def test_earliest_definition_at_the_bottom(self):
        # r1 is defined before r0: r0 goes on top
        points = {"r0": (1, 1, 0, 0), "r1": (0, 0, 3, 0)}
        assert return_order([["r0", "r1"]], points) == [0, 1]
        assert return_order([["r1", "r0"]], points) == [1, 0]

    def test_argument_returned_is_the_earliest(self):
        points = {"x": (0, 0, 0, 0), "a": (-1, 0, 0, 0)}
        assert return_order([["a", "x"]], points) == [1, 0]

    def test_constants_on_top(self):
        points = {"x": (0, 0, 0, 0)}
        assert return_order([["x", "0x00"]], points) == [1, 0]

    def test_ties_keep_yul_order(self):
        assert return_order([["0x01", "0x02"]], {}) == [0, 1]

    def test_ranks_added_over_return_blocks(self):
        # In the first block r0 is earlier, in the other two blocks s1 / t1 are earlier
        points = {"r0": (0, 0, 0, 0), "r1": (1, 0, 0, 0), "s0": (2, 0, 0, 0), "s1": (1, 0, 0, 0),
                  "t0": (2, 0, 0, 0), "t1": (1, 0, 0, 0)}
        assert return_order([["r0", "r1"], ["s0", "s1"], ["t0", "t1"]], points) == [0, 1]


class TestTraversal:

    def test_uses_and_definitions_along_the_chain(self):
        block_list = chain_block_list([
            [CFGInstruction("add", ["b", "0x01"], ["x"])],
            [CFGInstruction("mul", ["a", "x"], ["y"]), CFGInstruction("calldataload", ["a"], ["z"])],
        ])
        order = block_order(block_list)
        assert order == {"B0": (0, 0), "B1": (1, 1)}
        uses = first_uses(block_list, order)
        assert uses["b"][:2] == (0, 0) and uses["a"][:2] == (1, 0) and uses["x"][:2] == (1, 0)
        points = definition_points(block_list, order, ["a", "b"])
        assert points["a"] < points["b"] < points["x"] < points["y"] < points["z"]


class TestFunctionConvention:

    def test_permutations(self):
        convention = FunctionConvention("f", [2, 0, 1], [1, 0])
        assert convention.arguments(["a", "b", "c"]) == ["c", "a", "b"]
        assert convention.returned_values(["r0", "r1"]) == ["r1", "r0"]


class TestValidationMatches:

    def test_constants_are_aliased(self):
        assert _matches(["24", "v18", "s0", "26", "v18"], ["24", "v18", "0x40", "26"], False)
        assert not _matches(["24", "v19", "s0", "26"], ["24", "v18", "0x40", "26"], False)

    def test_values_aliased_in_the_block(self):
        # Two equal PUSHIMMUTABLE in the block are merged into the first one by build_spec
        assert _matches(["29", "v43", "v43", "40"], ["29", "v46", "v45", "40"], False, {"v43", "v45", "v46"})
        assert not _matches(["29", "v43", "v43", "40"], ["29", "v46", "v45", "40"], False, {"v43"})

    def test_forgotten_elements_only_if_allowed(self):
        assert _matches([], ["v56", "v57"], True)
        assert _matches(["v56"], ["v56", "v57"], True)
        assert not _matches(["v56"], ["v56", "v57"], False)


@pytest.mark.slow
@pytest.mark.parametrize("mode", ["args", "orders"])
def test_base64_end_to_end(mode: str, tmp_path: Path):
    """
    The conventions pass every --debug check (including validate_calling_conventions) on base64
    """
    output_folder = tmp_path.joinpath(mode)
    command = ["python3", str(REPO_ROOT.joinpath("src/grey_main.py")), "-s", str(BASE64), "-o", str(output_folder),
               "-if", "standard-json", "-solc", str(SOLC), "--debug", "--call-convention", mode]
    subprocess.run(command, cwd=tmp_path, check=True, capture_output=True)
    assert not pd.read_csv(output_folder.joinpath(f"{BASE64.stem}.csv")).empty
