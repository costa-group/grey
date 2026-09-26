"""
Script for analysing why solc's legacy block deduplicator removes more code from solc's own assembly than from
grey's. For a contract, it compares grey's assembly (the "<contract>_standard_json_output.json" fed to the importer,
before solc's optimizer) with solc's own via-IR assembly without deduplication nor inliner, using the same
standard-json input and solc binary.

Blocks are the sequences of assembly items from a tag to the next one. Subcommands:
  dups      duplicate blocks: exact (what the deduplicator can merge directly) and ignoring the tag values
            (what could be merged if the jump targets were merged as well)
  simulate  simulates the deduplicator (iteratively merging identical blocks ending in a jump or a terminal
            instruction, whose pushed tags point to already merged blocks) and classifies the unmerged duplicates
            ignoring tags (falling through, or pushing different targets)
  kinds     most frequent blocks removed by the simulated deduplication, in both assemblies
  trace     for the most repeated blocks (optionally containing a pattern), follows the tags they push level by
            level, showing how many distinct targets and codes appear (where the copies stop being identical)

Usage:
  python3 dedup_analysis.py <subcommand> <grey standard_json_output.json> <standard-json input> <contract>
      [--solc ./solc-latest] [--pattern TEXT] [--depth 4]
Findings obtained with it are in QUESTIONS.md (Q9 and later) and PROGRESS.md.
"""

import argparse
import collections
import json
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
BLOCK_ENDS = {"JUMP", "RETURN", "STOP", "REVERT", "INVALID", "SELFDESTRUCT"}

block_T = List[Tuple[str, Optional[str]]]


def runtime_code(assembly: Dict) -> List[Dict]:
    """
    Code of the runtime subobject (the first entry of .data), or the code itself if there is no subobject
    """
    data = assembly.get(".data", {})
    return data["0"][".code"] if "0" in data and ".code" in data["0"] else assembly[".code"]


def grey_code(grey_file: Path) -> List[Dict]:
    return runtime_code(next(iter(json.load(open(grey_file))["sources"].values()))["assemblyJson"])


def solc_code(source: Path, contract: str, solc_executable: str) -> List[Dict]:
    standard_json = json.loads(source.read_text())
    settings = standard_json.setdefault("settings", {})
    settings["viaIR"] = True
    settings["metadata"] = {"appendCBOR": False, "useLiteralContent": False, "bytecodeHash": "none"}
    settings["outputSelection"] = {"*": {contract: ["evm.legacyAssembly"]}}
    settings["optimizer"] = {"enabled": True, "details": {"inliner": False, "deduplicate": False}}
    completed = subprocess.run([solc_executable, "--standard-json"], input=json.dumps(standard_json),
                               capture_output=True, text=True, cwd=source.parent)
    output = json.loads(completed.stdout)
    contract_info = next(file_contracts[contract] for file_contracts in output["contracts"].values()
                         if contract in file_contracts)
    return runtime_code(contract_info["evm"]["legacyAssembly"])


def tagged_blocks(code: List[Dict]) -> List[Tuple[str, block_T]]:
    blocks, tag, current = [], None, []
    for item in code:
        if item["name"] == "tag":
            blocks.append((tag, current))
            tag, current = item["value"], []
        else:
            current.append((item["name"], item.get("value")))
    blocks.append((tag, current))
    return [(tag, block) for tag, block in blocks if tag is not None]


def text(block: block_T) -> str:
    return " ".join(name + ("" if value is None or name == "PUSH [tag]" else " " + str(value)) for name, value in block)


def without_tags(block: block_T) -> Tuple:
    return tuple((name, None if name == "PUSH [tag]" else value) for name, value in block)


def simulate(code: List[Dict]) -> Tuple[List[Tuple[str, block_T]], Dict[str, str]]:
    """
    Iterative deduplication: returns the blocks and the representative of each tag
    """
    blocks = tagged_blocks(code)
    representative = {tag: tag for tag, _ in blocks}

    def key(block):
        return tuple((name, representative.get(value, value) if name == "PUSH [tag]" else value) for name, value in block)

    changed = True
    while changed:
        changed = False
        seen = {}
        for tag, block in blocks:
            if representative[tag] != tag or not block or block[-1][0] not in BLOCK_ENDS:
                continue
            block_key = key(block)
            if block_key in seen and seen[block_key] != tag:
                representative[tag] = seen[block_key]
                changed = True
            else:
                seen.setdefault(block_key, tag)
    return blocks, representative


def cmd_dups(code: List[Dict], label: str) -> None:
    blocks = [block for _, block in tagged_blocks(code)]
    exact = collections.Counter(tuple(block) for block in blocks)
    ignoring = collections.Counter(without_tags(block) for block in blocks)
    print(f"{label:24s} blocks {len(blocks):5d} | duplicates exact {sum(c - 1 for c in exact.values() if c > 1):4d}"
          f" | ignoring tags {sum(c - 1 for c in ignoring.values() if c > 1):4d}")


def cmd_simulate(code: List[Dict], label: str) -> None:
    blocks, representative = simulate(code)
    groups = collections.defaultdict(list)
    for tag, block in blocks:
        groups[without_tags(block)].append((tag, block))
    falling, different_targets = 0, 0
    for group in groups.values():
        if len(group) < 2 or len({representative[tag] for tag, _ in group}) == 1:
            continue
        for tag, block in group[1:]:
            if representative[tag] != tag:
                continue
            if not block or block[-1][0] not in BLOCK_ENDS:
                falling += 1
            else:
                different_targets += 1
    merged = sum(1 for tag in representative if representative[tag] != tag)
    print(f"{label:24s} blocks {len(blocks):5d} | merged {merged:4d} | unmerged duplicates ignoring tags: "
          f"falling through {falling:4d}, different targets {different_targets:4d}")


def cmd_kinds(code: List[Dict], label: str, top: int = 8) -> None:
    blocks, representative = simulate(code)
    removed = collections.Counter(text(block) for tag, block in blocks if representative[tag] != tag)
    print(f"{label}: removed {sum(removed.values())} blocks")
    for block_text, count in removed.most_common(top):
        print(f"   {count:3d} x {block_text[:150]}")


def cmd_trace(code: List[Dict], label: str, pattern: Optional[str], depth: int) -> None:
    blocks = tagged_blocks(code)
    by_tag = {tag: block for tag, block in blocks}
    groups = collections.defaultdict(list)
    for tag, block in blocks:
        groups[text(block)].append(tag)
    print(f"== {label}")
    for block_text, tags in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        if len(tags) < 5 or (pattern and pattern not in block_text):
            continue
        print(f" {len(tags):3d} x {block_text[:120]}")
        level = tags
        for current_depth in range(depth):
            positions = collections.defaultdict(list)
            for tag in level:
                for i, value in enumerate(v for n, v in by_tag.get(tag, []) if n == "PUSH [tag]"):
                    positions[i].append(value)
            if not positions:
                break
            description, next_level = [], []
            for i, targets in positions.items():
                distinct = sorted(set(targets))
                codes = {text(by_tag[t]) if t in by_tag else "<outside>" for t in distinct}
                description.append(f"pos{i}: {len(distinct)} targets, {len(codes)} codes")
                if len(distinct) > 1:
                    next_level = distinct
            print(f"   level {current_depth + 1}: " + "; ".join(description))
            if len(next_level) < 2:
                break
            for target_text, count in collections.Counter(text(by_tag[t]) for t in next_level if t in by_tag).most_common(3):
                print(f"      {count:3d} x {target_text[:140]}")
            level = next_level


def main():
    parser = argparse.ArgumentParser(description="Analyse solc's block deduplication on grey vs solc assembly")
    parser.add_argument("subcommand", choices=["dups", "simulate", "kinds", "trace"])
    parser.add_argument("grey_file", type=Path)
    parser.add_argument("source", type=Path)
    parser.add_argument("contract")
    parser.add_argument("--solc", default=str(REPO_ROOT.joinpath("solc-latest")))
    parser.add_argument("--pattern", default=None)
    parser.add_argument("--depth", type=int, default=4)
    args = parser.parse_args()

    codes = [("grey (pre-import)", grey_code(args.grey_file)),
             ("solc no dedup/inliner", solc_code(args.source.resolve(), args.contract, str(Path(args.solc).resolve())))]
    for label, code in codes:
        if args.subcommand == "dups":
            cmd_dups(code, label)
        elif args.subcommand == "simulate":
            cmd_simulate(code, label)
        elif args.subcommand == "kinds":
            cmd_kinds(code, label)
        else:
            cmd_trace(code, label, args.pattern, args.depth)


if __name__ == "__main__":
    main()
