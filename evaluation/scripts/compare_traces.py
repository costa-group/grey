#!/usr/bin/env python3
"""
Where does a call spend more gas with one code than with another? Executes the same calldata on two contracts with
geth's `evm run --trace` (fresh state: suitable for calls that do not depend on storage, e.g. pure functions or loops)
and compares:
  - the executed opcodes (count per opcode and the difference);
  - the hottest basic blocks (executions × stack instructions);
  - one iteration of a loop (--iterations N: the trace is cut into N equal parts after a prologue), aligned on its
    non-stack instructions: the gaps where the stack instructions (DUP/SWAP/POP) or jumps differ are printed.

Usage:
    python3 evaluation/scripts/compare_traces.py --code solc=<creation hex or file> --code grey=<creation hex or file> \
        --calldata 30d1b5e7 [--iterations 1000] [--top 12] [--evm evm]
The creation codes are executed first to obtain the runtime codes. Written to locate the base64 regression
(PROGRESS 2026-10-01: +9 SWAPs per iteration in allocate_memory).
"""

import argparse
import collections
import difflib
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple

STACK = ("DUP", "SWAP", "POP")
CONTROL = ("JUMP", "JUMPI", "JUMPDEST")
TERMINATORS = {0x56, 0x57, 0x00, 0xf3, 0xfd, 0xfe, 0xff}


def read_code(value: str) -> str:
    path = Path(value)
    text = path.read_text().strip() if path.is_file() else value
    return text.removeprefix("0x")


def run_trace(evm: str, runtime: str, calldata: str) -> Tuple[List[Dict], int]:
    """
    Steps of the execution (pc and opName) and the gas used (geth's evm, no intrinsic gas)
    """
    completed = subprocess.run([evm, "run", "--input", calldata, "--gas", "1000000000", "--trace", "--nostack",
                                runtime], capture_output=True, text=True)
    steps, gas_used = [], None
    for line in completed.stderr.splitlines():
        if line.startswith('{"pc"'):
            step = json.loads(line)
            steps.append({"pc": step["pc"], "op": step["opName"]})
        elif '"gasUsed"' in line:
            gas_used = int(json.loads(line)["gasUsed"], 16)
    return steps, gas_used


def runtime_code(evm: str, creation: str) -> str:
    return subprocess.run([evm, "run", creation], capture_output=True, text=True).stdout.strip().removeprefix("0x")


def basic_blocks(code: bytes) -> List[List[Tuple[int, str]]]:
    """
    Basic blocks of a code (split at JUMPDEST and after the terminators) as lists of (pc, opcode name)
    """
    def name(op: int) -> str:
        if 0x60 <= op <= 0x7f:
            return f"PUSH{op - 0x5f}"
        if 0x80 <= op <= 0x8f:
            return f"DUP{op - 0x7f}"
        if 0x90 <= op <= 0x9f:
            return f"SWAP{op - 0x8f}"
        return {0x50: "POP", 0x56: "JUMP", 0x57: "JUMPI", 0x5b: "JUMPDEST", 0x5f: "PUSH0"}.get(op, f"op{op:02x}")

    blocks, current, pc = [], [], 0
    while pc < len(code):
        op = code[pc]
        if op == 0x5b and current:
            blocks.append(current)
            current = []
        current.append((pc, name(op)))
        if op in TERMINATORS:
            blocks.append(current)
            current = []
        pc += 1 + (op - 0x5f if 0x60 <= op <= 0x7f else 0)
    if current:
        blocks.append(current)
    return blocks


def hot_blocks(runtime: str, steps: List[Dict], top: int) -> List[str]:
    executed = collections.Counter(step["pc"] for step in steps)
    rows = []
    for block in basic_blocks(bytes.fromhex(runtime)):
        count = executed[block[0][0]]
        if count:
            stack = sum(1 for _, op in block if op.startswith(STACK))
            rows.append((count * stack, count, block[0][0], stack, " ".join(op for _, op in block)))
    rows.sort(reverse=True)
    return [f"  x{count:<6} pc {pc:<5} stack {stack:<3} | {ops}" for _, count, pc, stack, ops in rows[:top]]


def gaps(steps: List[Dict]) -> Tuple[List[str], List[List[str]]]:
    """
    The non-stack instructions and, for each one, the stack and control instructions executed right before it
    """
    semantic, before, current = [], [], []
    for step in steps:
        op = step["op"]
        if op.startswith(STACK) or op.startswith("PUSH") or op in CONTROL:
            current.append(op)
        else:
            semantic.append(op)
            before.append(current)
            current = []
    return semantic, before


def align_iteration(names: List[str], traces: List[List[Dict]], iterations: int) -> List[str]:
    """
    Aligns the middle iteration of both traces (cut into equal parts) on their non-stack instructions
    """
    slices = []
    for steps in traces:
        size = (len(steps) - 40) // iterations
        start = 20 + (iterations // 2) * size
        slices.append(steps[start:start + size])
    (semantic_a, gaps_a), (semantic_b, gaps_b) = gaps(slices[0]), gaps(slices[1])
    matcher = difflib.SequenceMatcher(a=semantic_a, b=semantic_b, autojunk=False)
    lines = [f"  iteration: {len(slices[0])} / {len(slices[1])} steps, {len(semantic_a)} / {len(semantic_b)} non-stack "
             f"instructions (a rotation of the cut shows as an insert/delete at the ends)"]
    stack_count = lambda ops: sum(1 for op in ops if op.startswith(STACK))
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                before_a, before_b = gaps_a[i1 + offset], gaps_b[j1 + offset]
                if stack_count(before_a) != stack_count(before_b) or before_a.count("JUMP") != before_b.count("JUMP"):
                    lines.append(f"  before {semantic_a[i1 + offset]:<12} {names[0]}: {' '.join(before_a)}")
                    lines.append(f"  {'':<19} {names[1]}: {' '.join(before_b)}")
        else:
            lines.append(f"  {tag}: {names[0]} {semantic_a[i1:i2]} / {names[1]} {semantic_b[j1:j2]}")
    return lines


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--code", action="append", required=True, type=lambda value: tuple(value.split("=", 1)),
                        help="NAME=creation code (hex or file); exactly two")
    parser.add_argument("--calldata", required=True)
    parser.add_argument("--iterations", type=int, default=None, help="Number of iterations of the loop to align")
    parser.add_argument("--top", type=int, default=12)
    parser.add_argument("--evm", default="evm", help="geth's evm binary")
    args = parser.parse_args()
    assert len(args.code) == 2, "Give exactly two codes"

    names, runtimes, traces = [], [], []
    for name, value in args.code:
        runtime = runtime_code(args.evm, read_code(value))
        steps, gas_used = run_trace(args.evm, runtime, args.calldata.removeprefix("0x"))
        names.append(name)
        runtimes.append(runtime)
        traces.append(steps)
        print(f"{name}: runtime {len(runtime) // 2} bytes, {len(steps)} steps, gas {gas_used:,}")

    counts = [collections.Counter(step["op"] for step in steps) for steps in traces]
    print(f"\nexecuted opcodes that differ ({names[1]} - {names[0]}):")
    for op in sorted(set(counts[0]) | set(counts[1])):
        if counts[0][op] != counts[1][op]:
            print(f"  {op:<10} {counts[0][op]:>9} {counts[1][op]:>9} {counts[1][op] - counts[0][op]:>+9}")
    for name, runtime, steps in zip(names, runtimes, traces):
        print(f"\nhottest blocks of {name} (executions x stack instructions):")
        print("\n".join(hot_blocks(runtime, steps, args.top)))
    if args.iterations:
        print(f"\none iteration aligned:")
        print("\n".join(align_iteration(names, traces, args.iterations)))


if __name__ == "__main__":
    main()
