"""
Script for comparing the reparation phase (memory slots used to hold stack-too-deep values)
and the final bytecode size between two versions of grey (e.g. before and after a change).

Each version is given by the path to its "src" folder. grey is executed on every input with the
same flags, in a separate working directory per run. The results are read from the CSVs grey
stores in the output folder:
  - repair_<stem>.csv: one row per repaired block list (num_colors, memory_slots, ...)
  - <stem>.csv: one row per contract with the number of bytes of the bytecode
The output folder of each run is removed once the CSVs are read (unless --keep-outputs), as the
full outputs of a corpus require several GB. The log of each run is kept in <output_dir>/logs.

Inputs can be given explicitly (the input format is inferred from the extension) or extracted from
the run configurations of an IntelliJ/PyCharm workspace (--from-workspace), using the "-s", "-if",
"-solc" and "-c" options of each configuration.

Older versions of grey are nondeterministic (their output depends on the hash seed). For such
versions, several seeds can be given (--seeds-before / --seeds-after) and the minimum and maximum
values of each metric are reported. By default, PYTHONHASHSEED is left unset.

Usage:
  python3 compare_repair_slots.py <src_before> <src_after> <output_dir> [<input_1> ... <input_n>]
      [--from-workspace .idea/workspace.xml] [--depths 16,8] [--flags "<grey flags>"]
      [--seeds-before 0,1,2] [--seeds-after 0] [--jobs N] [--keep-outputs]
A single flag must be passed as --flags=--no-inline (argparse reads "--flags --no-inline" as two options).
"""

import argparse
import hashlib
import os
import shlex
import shutil
import subprocess
import xml.etree.ElementTree as ElementTree
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

DEFAULT_FLAGS = "--no-inline"
METRICS = ["repaired_block_lists", "num_colors", "memory_slots", "redundant_stores", "num_bytes"]
REPO_ROOT = Path(__file__).resolve().parent.parent


def input_format_from_extension(input_file: Path) -> str:
    """
    Infers the grey input format from the file extension
    """
    if input_file.suffix == ".sol":
        return "sol"
    if input_file.suffix == ".json" and not input_file.name.endswith("yul_cfg.json"):
        return "standard-json"
    return "yul-cfg"


def inputs_from_workspace(workspace_file: Path, default_solc: Path) -> Tuple[List[Dict], List[str]]:
    """
    Extracts the distinct inputs from the run configurations in the workspace. Returns the list
    of inputs (dicts with source, input_format, solc and contract) and the list of skipped entries
    """
    tree = ElementTree.parse(workspace_file)
    inputs, skipped, already_seen = [], [], set()
    for option in tree.iter("option"):
        if option.get("name") != "PARAMETERS" or "-s" not in (option.get("value") or ""):
            continue
        tokens = shlex.split(option.get("value"))
        options = {token: tokens[i + 1] for i, token in enumerate(tokens[:-1])
                   if token in ["-s", "-if", "-solc", "-c"]}
        if "-s" not in options:
            continue
        source = REPO_ROOT.joinpath(options["-s"]).resolve()
        if not source.is_file():
            skipped.append(options["-s"])
            continue
        # The solc binary configured is used if it exists (some point to other machines)
        solc = REPO_ROOT.joinpath(options.get("-solc", "")).resolve() if "-solc" in options else default_solc
        if not solc.is_file():
            solc = default_solc
        input_info = {"source": source, "input_format": options.get("-if", "yul-cfg"),
                      "solc": solc, "contract": options.get("-c")}
        key = (source, input_info["input_format"], solc, input_info["contract"])
        if key not in already_seen:
            already_seen.add(key)
            inputs.append(input_info)
    return inputs, skipped


def run_identifier(input_info: Dict) -> str:
    """
    Unique and readable identifier of an input (the same source can appear with several options)
    """
    key = f"{input_info['source']}|{input_info['input_format']}|{input_info['solc']}|{input_info['contract']}"
    return f"{input_info['source'].stem}_{hashlib.sha1(key.encode()).hexdigest()[:8]}"


def run_grey(src_folder: Path, input_info: Dict, output_folder: Path, flags: str,
             hash_seed: Optional[str], log_file: Path) -> Tuple[Path, Optional[str]]:
    """
    Runs grey on a single input, storing the results in output_folder and the log in log_file.
    Returns the output folder and the error message (None if the execution succeeded)
    """
    output_folder.mkdir(parents=True, exist_ok=True)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    command = ["python3", str(src_folder.joinpath("grey_main.py")), "-s", str(input_info["source"]),
               "-o", str(output_folder), "-if", input_info["input_format"],
               "-solc", str(input_info["solc"]), *shlex.split(flags)]
    if input_info.get("contract") is not None:
        command += ["-c", input_info["contract"]]

    environment = dict(os.environ)
    if hash_seed is not None:
        environment["PYTHONHASHSEED"] = hash_seed

    completed = subprocess.run(command, cwd=output_folder, capture_output=True, text=True, env=environment)
    log_file.write_text(" ".join(command) + "\n" + completed.stdout + completed.stderr)
    if completed.returncode != 0:
        last_error_line = (completed.stderr.strip().splitlines() or ["unknown error"])[-1]
        return output_folder, last_error_line
    return output_folder, None


def collect_results(output_folder: Path, input_file: Path) -> Dict[str, float]:
    """
    Aggregates the repair statistics and the bytecode size of a single execution
    """
    repair_csv = output_folder.joinpath(f"repair_{input_file.stem}.csv")
    contracts_csv = output_folder.joinpath(f"{input_file.stem}.csv")

    def read_csv(csv_file: Path) -> pd.DataFrame:
        return pd.read_csv(csv_file) if csv_file.exists() and csv_file.stat().st_size > 1 else pd.DataFrame()

    repair_df, contracts_df = read_csv(repair_csv), read_csv(contracts_csv)

    def column_sum(dataframe: pd.DataFrame, column: str) -> float:
        return float(dataframe[column].sum()) if column in dataframe.columns else 0.0

    return {"repaired_block_lists": len(repair_df),
            "num_colors": column_sum(repair_df, "num_colors"),
            "memory_slots": column_sum(repair_df, "memory_slots"),
            "redundant_stores": column_sum(repair_df, "redundant_stores"),
            "num_bytes": column_sum(contracts_df, "num_bytes")}


def run_and_collect(src_folder: Path, input_info: Dict, output_folder: Path, flags: str,
                    hash_seed: Optional[str], log_file: Path, keep_outputs: bool) -> Tuple[Optional[str], Dict]:
    """
    Runs grey and collects the results, removing the output folder afterwards if requested
    """
    _, error = run_grey(src_folder, input_info, output_folder, flags, hash_seed, log_file)
    results = collect_results(output_folder, input_info["source"]) if error is None else {}
    if not keep_outputs:
        shutil.rmtree(output_folder, ignore_errors=True)
    return error, results


def parse_list(value: Optional[str]) -> List[Optional[str]]:
    """
    Parses a comma-separated list. An empty value corresponds to a single run without seed
    """
    return [element.strip() for element in value.split(",")] if value else [None]


def main():
    parser = argparse.ArgumentParser(description="Compare the reparation results of two grey versions")
    parser.add_argument("src_before", type=Path)
    parser.add_argument("src_after", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("inputs", type=Path, nargs="*")
    parser.add_argument("--from-workspace", type=Path, dest="workspace", default=None)
    parser.add_argument("--depths", type=str, default="8", help="Comma-separated list of -d values")
    parser.add_argument("--flags", type=str, default=DEFAULT_FLAGS)
    parser.add_argument("--solc", type=Path, default=REPO_ROOT.joinpath("examples/solc-without-opt"))
    parser.add_argument("--seeds-before", type=str, default=None, dest="seeds_before")
    parser.add_argument("--seeds-after", type=str, default=None, dest="seeds_after")
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--keep-outputs", action="store_true", dest="keep_outputs")
    args = parser.parse_args()

    solc_executable = args.solc.resolve()
    inputs = [{"source": input_file.resolve(), "input_format": input_format_from_extension(input_file),
               "solc": solc_executable, "contract": None} for input_file in args.inputs]
    if args.workspace is not None:
        workspace_inputs, skipped = inputs_from_workspace(args.workspace, solc_executable)
        inputs.extend(workspace_inputs)
        for skipped_entry in skipped:
            print(f"Skipped (not a file): {skipped_entry}")

    versions = {"before": (args.src_before.resolve(), parse_list(args.seeds_before)),
                "after": (args.src_after.resolve(), parse_list(args.seeds_after))}
    depths = [depth.strip() for depth in args.depths.split(",")]
    output_dir = args.output_dir.resolve()

    # Launch every (version, seed, input, depth) combination in parallel
    tasks = {}
    with ProcessPoolExecutor(max_workers=args.jobs) as executor:
        for version_name, (src_folder, seeds) in versions.items():
            for seed in seeds:
                for input_info in inputs:
                    for depth in depths:
                        run_name = f"{run_identifier(input_info)}_d{depth}_s{seed}"
                        output_folder = output_dir.joinpath("runs", version_name, run_name)
                        log_file = output_dir.joinpath("logs", version_name, f"{run_name}.txt")
                        flags = f"{args.flags} -d {depth}"
                        tasks[(version_name, seed, run_identifier(input_info), depth)] = executor.submit(
                            run_and_collect, src_folder, input_info, output_folder, flags, seed,
                            log_file, args.keep_outputs)

    rows = []
    for input_info in inputs:
        for depth in depths:
            row = {"input": run_identifier(input_info), "source": str(input_info["source"]),
                   "input_format": input_info["input_format"], "depth": int(depth)}
            for version_name, (_, seeds) in versions.items():
                errors, results_per_seed = [], []
                for seed in seeds:
                    error, results = tasks[(version_name, seed, run_identifier(input_info), depth)].result()
                    errors.append(error)
                    if error is None:
                        results_per_seed.append(results)
                row[f"error_{version_name}"] = next((error for error in errors if error is not None), None)
                if results_per_seed:
                    for metric in METRICS:
                        values = [results[metric] for results in results_per_seed]
                        row[f"{metric}_{version_name}_min"] = min(values)
                        row[f"{metric}_{version_name}_max"] = max(values)
                    row[f"deterministic_{version_name}"] = all(results == results_per_seed[0]
                                                               for results in results_per_seed)
            rows.append(row)

    comparison = pd.DataFrame(rows).sort_values(["input", "depth"])
    comparison.to_csv(output_dir.joinpath("comparison.csv"), index=False)

    print(f"Inputs: {len(inputs)} x depths {depths}")
    for depth in depths:
        depth_rows = comparison[comparison["depth"] == int(depth)]
        both_ok = depth_rows[depth_rows["error_before"].isna() & depth_rows["error_after"].isna()]
        print(f"== depth {depth}: {len(depth_rows)} runs, succeeded in both versions: {len(both_ok)}")
        for version_name in versions:
            failed = depth_rows[depth_rows[f"error_{version_name}"].notna()]
            for _, failed_row in failed.iterrows():
                print(f"  [{version_name}] {failed_row['input']}: {failed_row[f'error_{version_name}']}")
            if len(versions[version_name][1]) > 1:
                nondeterministic = int((~both_ok[f"deterministic_{version_name}"].astype(bool)).sum())
                print(f"  [{version_name}] inputs with different results across seeds: {nondeterministic}")

        for metric in METRICS:
            before_min, before_max = both_ok[f"{metric}_before_min"], both_ok[f"{metric}_before_max"]
            after = both_ok[f"{metric}_after_min"]
            print(f"  {metric}: before={before_min.sum():.0f}..{before_max.sum():.0f} after={after.sum():.0f} "
                  f"(better than every seed: {int((after < before_min).sum())}, "
                  f"worse than every seed: {int((after > before_max).sum())})")


if __name__ == "__main__":
    main()
