"""
Diagnostic that runs grey and reports how often structurally equivalent blocks get identical specifications
(the input to the greedy), by kind of block. Two blocks are structurally equivalent if they have the same jump
type, the same instructions (constants kept, variables abstracted) and equivalent successors (recursively).
Specifications are compared after renaming the variables by order of appearance and ignoring tag values.
Kinds:
  revert path                   admits junk and every reachable exit reverts
  never returns (success exit)  admits junk and some exit returns successfully (return / stop)
  loop                          inside a loop
  returning code                can reach a function return

A low proportion of identical specifications means that the stack layouts of equivalent code depend on the
context, which prevents solc's deduplicator from merging the copies (see dedup_analysis.py for the assembly level).

Usage (from the repo root, with any grey arguments):
  python3 scripts/equivalent_specs_diag.py -s <input> -o <out_dir> -if standard-json -solc <solc> [grey flags]
"""

import atexit
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.joinpath("src")))

import networkx as nx  # noqa: E402
import liveness.layout_generation as layout_generation  # noqa: E402

BLOCKS = []

original_init = layout_generation.LayoutGeneration.__init__


def successful_exit(block) -> bool:
    if block.get_jump_type() in ["FunctionReturn", "mainExit"]:
        return True
    instructions = block.get_instructions()
    return block.get_jump_type() == "terminal" and len(instructions) > 0 and \
        instructions[-1].get_op_name() in {"return", "stop", "selfdestruct"}


def recording_init(self, *args, **kwargs):
    original_init(self, *args, **kwargs)
    # Blocks that admit junk and from which no successful exit can be reached
    reaches_success = set()
    for block_id in self._cfg_graph.nodes:
        if successful_exit(self._block_list.get_block(block_id)):
            reaches_success.add(block_id)
            reaches_success.update(nx.ancestors(self._cfg_graph, block_id))
    revert_region = {block_id for block_id in self._block_list.blocks
                     if self._can_have_junk(block_id) and block_id not in reaches_success}
    for block_id in self._block_list.blocks:
        if block_id in revert_region:
            kind = "revert path"
        elif block_id in self._loop_nesting_forest:
            kind = "loop"
        elif self._can_have_junk(block_id):
            kind = "never returns (success exit)"
        else:
            kind = "returning code"
        BLOCKS.append((self._block_list, self._block_list.get_block(block_id), kind))


layout_generation.LayoutGeneration.__init__ = recording_init


def renamed(values, mapping):
    result = []
    for value in values:
        if isinstance(value, str) and value.isdigit():
            result.append("tag")
        elif isinstance(value, str) and not value.startswith("0x"):
            mapping.setdefault(value, f"x{len(mapping)}")
            result.append(mapping[value])
        else:
            result.append(value)
    return result


def spec_key(spec):
    mapping = {}
    source = renamed(spec["src_ws"], mapping)
    instructions = tuple((instr["disasm"], tuple(renamed(instr["inpt_sk"], mapping)),
                          tuple(renamed(instr["outpt_sk"], mapping)),
                          "tag" if instr["disasm"] == "PUSH [TAG]" else json.dumps(instr.get("value")))
                         for instr in spec["user_instrs"])
    return tuple(source), instructions, tuple(renamed(spec["tgt_ws"], mapping))


def structural_key(block_list, block, memo):
    if block.block_id in memo:
        return memo[block.block_id]
    memo[block.block_id] = None
    instructions = tuple((instr.get_op_name(), tuple(arg if arg.startswith("0x") else "_" for arg in instr.get_in_args()),
                          len(instr.get_out_args()))
                         for instr in block.get_instructions() if instr.get_op_name() != "PUSH [tag]")
    successors = tuple(structural_key(block_list, block_list.get_block(successor), memo) for successor in block.successors)
    memo[block.block_id] = (block.get_jump_type(), instructions, successors)
    return memo[block.block_id]


def report():
    groups = collections.defaultdict(list)
    for block_list, block, kind in BLOCKS:
        groups[structural_key(block_list, block, {})].append((block, kind))
    blocks_per_kind = collections.Counter(kind for _, _, kind in BLOCKS)
    copies, identical = collections.Counter(), collections.Counter()
    for group in groups.values():
        if len(group) < 2:
            continue
        seen = set()
        for i, (block, kind) in enumerate(group):
            key = spec_key(block.spec)
            if i > 0:
                copies[kind] += 1
                identical[kind] += key in seen
            seen.add(key)
    print(f"{'kind':32s} {'blocks':>7s} {'copies':>7s} {'identical specs':>16s}")
    for kind in sorted(blocks_per_kind):
        print(f"{kind:32s} {blocks_per_kind[kind]:7d} {copies[kind]:7d} {identical[kind]:16d}")


atexit.register(report)

from execution.args_parser import parse_args  # noqa: E402
from execution.main_execution import main  # noqa: E402

main(parse_args())
