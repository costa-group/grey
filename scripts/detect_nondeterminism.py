"""
Script for detecting nondeterminism in grey: the same input is executed under several hash seeds
(PYTHONHASHSEED), and the results are compared. If the bytecode differs, the intermediate artifacts
generated with "-v --debug" are compared following the order of the pipeline, reporting the first
stage in which they diverge and the files that differ. This points to the pass that iterates over
a set (or any other hash-dependent structure) in a way that reaches the output.

Stages, in pipeline order (see the -v dumps):
  liveness/<step>   dot files after each preprocessing step (initial, renamed, inlined, combined,
                    jumps, split, constants)
  sfs               block specifications fed to the greedy algorithm (stack_layouts/*/sfs)
  layouts           stack layouts (stack_layouts/*/layouts)
  repair/<step>     greedy ids during the reparation (annotated_vget, repaired_vget)
  asm               final greedy ids per block (asm)
  bytecode          final bytecode

Python sets inside dot labels are printed in hash order, so every "{...}" literal is normalized
by sorting its elements before comparing.

Usage:
  python3 detect_nondeterminism.py <src_folder> <output_dir> <input_1> ... <input_n>
      [--seeds 1,2,3] [--flags "-d 8 --no-inline"] [--jobs N]
"""

import argparse
import json
import re
import shutil
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compare_repair_slots import run_grey, input_format_from_extension, REPO_ROOT

SET_LITERAL = re.compile(r"\{([^{}]*)\}")

# (stage name, glob pattern relative to the output folder of a run)
STAGES = [(f"liveness/{step}", f"*/liveness/{step}/**/*.dot")
          for step in ["initial", "renamed", "inlined", "combined", "jumps", "split", "constants"]] + \
         [("sfs", "*/stack_layouts/**/sfs/*.json"),
          ("layouts", "*/stack_layouts/**/layouts/*.dot"),
          ("repair/annotated_vget", "*/repair/**/annotated_vget/*.dot"),
          ("repair/repaired_vget", "*/repair/**/repaired_vget/*.dot"),
          ("asm", "*/asm/*.dot")]


def normalize_set_literals(text: str) -> str:
    """
    Sorts the elements of every set literal, so that the hash order does not produce differences
    """
    return SET_LITERAL.sub(lambda match: "{" + ", ".join(sorted(element.strip() for element in
                                                               match.group(1).split(","))) + "}", text)


def normalized_contents(artifact: Path) -> str:
    if artifact.suffix == ".json":
        return json.dumps(json.loads(artifact.read_text()), sort_keys=True, indent=1)
    # Graphviz splits long labels with a backslash + newline, possibly inside a set literal
    return normalize_set_literals(artifact.read_text().replace("\\\n", ""))


def bytecode_of_run(output_folder: Path, input_file: Path) -> Optional[str]:
    contracts_csv = output_folder.joinpath(f"{input_file.stem}.csv")
    return contracts_csv.read_text() if contracts_csv.exists() else None


def first_divergence(run_folders: List[Path]) -> Tuple[Optional[str], List[str]]:
    """
    Compares the artifacts of several runs of the same input stage by stage. Returns the first
    stage that differs and the relative paths of the files that differ in that stage
    """
    reference = run_folders[0]
    for stage_name, pattern in STAGES:
        reference_files = {path.relative_to(reference) for path in reference.glob(pattern)}
        differing = set()
        for other in run_folders[1:]:
            other_files = {path.relative_to(other) for path in other.glob(pattern)}
            differing.update(str(path) for path in reference_files.symmetric_difference(other_files))
            for relative_path in reference_files.intersection(other_files):
                if normalized_contents(reference.joinpath(relative_path)) != \
                        normalized_contents(other.joinpath(relative_path)):
                    differing.add(str(relative_path))
        if differing:
            return stage_name, sorted(differing)
    return None, []


def main():
    parser = argparse.ArgumentParser(description="Detect nondeterministic outputs in grey")
    parser.add_argument("src_folder", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("inputs", type=Path, nargs="+")
    parser.add_argument("--seeds", type=str, default="1,2,3")
    parser.add_argument("--flags", type=str, default="-d 8 --no-inline")
    parser.add_argument("--solc", type=Path, default=REPO_ROOT.joinpath("examples/solc-without-opt"))
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--keep-outputs", action="store_true", dest="keep_outputs")
    args = parser.parse_args()

    seeds = [seed.strip() for seed in args.seeds.split(",")]
    flags = f"{args.flags} -v --debug"
    output_dir = args.output_dir.resolve()

    tasks: Dict[Tuple[Path, str], object] = {}
    with ProcessPoolExecutor(max_workers=args.jobs) as executor:
        for input_file in args.inputs:
            input_file = input_file.resolve()
            input_info = {"source": input_file, "input_format": input_format_from_extension(input_file),
                          "solc": args.solc.resolve(), "contract": None}
            for seed in seeds:
                run_folder = output_dir.joinpath(input_file.stem, f"seed_{seed}")
                tasks[(input_file, seed)] = executor.submit(run_grey, args.src_folder.resolve(), input_info,
                                                            run_folder, flags, seed, run_folder.joinpath("log.txt"))

    num_divergent = 0
    for input_file in dict.fromkeys(input_file for input_file, _ in tasks):
        run_folders, errors = [], []
        for seed in seeds:
            run_folder, error = tasks[(input_file, seed)].result()
            run_folders.append(run_folder)
            errors.append(error)

        bytecodes = [bytecode_of_run(run_folder, input_file) for run_folder in run_folders]
        if any(error is not None for error in errors):
            status = "error in some seed: " + "; ".join(str(error) for error in errors)
        elif len(set(bytecodes)) == 1:
            stage, _ = first_divergence(run_folders)
            status = "deterministic" if stage is None else f"same bytecode, intermediate divergence in {stage}"
        else:
            num_divergent += 1
            stage, differing_files = first_divergence(run_folders)
            status = f"DIVERGES: first stage {stage or 'bytecode'}; files: {differing_files[:5]}"
        print(f"{input_file.stem}: {status}")

        if not args.keep_outputs and status == "deterministic":
            shutil.rmtree(output_dir.joinpath(input_file.stem), ignore_errors=True)

    print(f"Inputs with different bytecode across seeds: {num_divergent}/{len(set(i for i, _ in tasks))}")
    sys.exit(1 if num_divergent > 0 else 0)


if __name__ == "__main__":
    main()
