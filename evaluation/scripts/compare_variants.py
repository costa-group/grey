"""
Script for comparing several variants of grey on the same inputs, each variant being a src folder plus extra
flags (e.g. the same src with different experimental switches). Every (variant, input, depth) is run once, so the
reference is not re-run for each comparison as with compare_repair_slots.py. For each run it records the metrics
of compare_repair_slots.py (repaired block lists, colours, memory slots, redundant stores, bytes), the memory
accesses of the reparation (VGET, VSET, DUP-VSET, from the repair CSV of grey) and, per contract, statistics of
the final bytecode obtained by a linear scan (see bytecode_statistics): bytes, basic blocks, terminal blocks,
JUMPDESTs, DUPs, SWAPs and POPs. Each input can also be compiled once with one or more solc references (via-IR, optimizer enabled,
as in compare_with_solc.py): --solc-reference uses the input's own solc (the one grey uses) and
--reference-solc NAME=PATH (repeatable) any other binary, e.g. the official release when grey runs with a build
without the legacy optimizer. The gap per variant and reference is reported over the contracts that the
reference compiles.

Outputs (in <output_dir>):
  - results.csv: one row per (variant, input, depth), with the error (if any), the metrics, the memory accesses
    and the bytecode statistics summed over the contracts (code_<statistic>)
  - contracts.csv: one row per (variant, input, depth, contract), with grey's bytecode statistics
    (grey_<statistic>) and those of each reference (solc_<name>_<statistic>)
  - a summary printed per depth, over the (input, depth) pairs where every variant succeeds: totals per variant,
    difference with the reference (the first variant) and with the previous variant in the given order
    (useful when the variants are cumulative iterations), with the number of better / worse inputs; the totals
    of the bytecode statistics and memory accesses per variant; and, over the contracts each reference compiles,
    the bytecode statistics of every variant next to the reference's.
The output folders of the runs are removed (the logs are kept in <output_dir>/logs).

Usage:
  python3 compare_variants.py <output_dir> --variant NAME=SRC[::FLAGS] [--variant ...]
      [inputs...] [--inputs-from FILE] [--from-workspace .idea/workspace.xml] [--depths 16,8] [--flags "--no-inline --debug"]
      [--jobs N] [--solc-reference] [--reference-solc NAME=PATH ...] [--force-solc ./solc-latest]
      [--keep-artifacts] [--timeout SECONDS]
Example of a variant: --variant "junk=/path/src::--junk-strategy simulated"
"""

import argparse
import csv
import gzip
import json
import shutil
import sys
import tarfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

import sys
# The comparison scripts shared with the other experiments stay in the repository's scripts/ (on grey-remote, every
# script is copied to the same folder)
REPOSITORY_SCRIPTS = Path(__file__).resolve().parent.parent.parent.joinpath("scripts")
if REPOSITORY_SCRIPTS.is_dir():
    sys.path.append(str(REPOSITORY_SCRIPTS))

from compare_repair_slots import (DEFAULT_FLAGS, METRICS, REPO_ROOT, collect_results, input_format_from_extension,
                                  inputs_from_workspace, run_grey, run_identifier)
from check_equivalence_hevm import link_placeholders
from compare_with_solc import grey_bytecodes, solc_bytecodes

# The bytecode of large contracts exceeds the default size of a CSV field (grey stores it in its CSVs)
csv.field_size_limit(sys.maxsize)

BYTECODE_STATISTICS = ["bytes", "instructions", "blocks", "terminal_blocks", "jumpdest", "jump", "dynamic_jump", "jumpi", "dup",
                       "swap", "pop"]
MEMORY_ACCESSES = ["num_vget", "num_vset", "num_dup_vset"]
# STOP, RETURN, REVERT, INVALID, SELFDESTRUCT
TERMINATING_OPCODES = {0x00, 0xf3, 0xfd, 0xfe, 0xff}
JUMP_OPCODES = {0x56, 0x57}


def bytecode_statistics(code: str) -> Dict[str, int]:
    """
    Statistics of a bytecode by a linear scan. A basic block starts at every JUMPDEST and after every JUMP, JUMPI
    or terminating instruction; terminal blocks are those ending in a terminating instruction. A dynamic jump is a
    JUMP not preceded by a PUSH (its target comes from the stack, e.g. a function return). Data sections
    (e.g. the runtime code inside the creation code is code, but constants appended after it are not) are
    scanned as code, in grey's and solc's bytecode alike
    """
    code_bytes = bytes.fromhex(link_placeholders(code))
    statistics = dict.fromkeys(BYTECODE_STATISTICS, 0)
    statistics["bytes"] = len(code_bytes)
    block_is_empty, position, previous_opcode = True, 0, None
    while position < len(code_bytes):
        opcode = code_bytes[position]
        statistics["instructions"] += 1
        if opcode == 0x5b:
            statistics["jumpdest"] += 1
            if not block_is_empty:
                statistics["blocks"] += 1
            block_is_empty = False
        else:
            block_is_empty = False
            if 0x80 <= opcode <= 0x8f:
                statistics["dup"] += 1
            elif 0x90 <= opcode <= 0x9f:
                statistics["swap"] += 1
            elif opcode == 0x50:
                statistics["pop"] += 1
            elif opcode == 0x56:
                statistics["jump"] += 1
                statistics["dynamic_jump"] += previous_opcode is None or not 0x60 <= previous_opcode <= 0x7f
            elif opcode == 0x57:
                statistics["jumpi"] += 1
            if opcode in JUMP_OPCODES or opcode in TERMINATING_OPCODES:
                statistics["blocks"] += 1
                statistics["terminal_blocks"] += opcode in TERMINATING_OPCODES
                block_is_empty = True
        previous_opcode = opcode
        position += 1 + (opcode - 0x5f if 0x60 <= opcode <= 0x7f else 0)
    statistics["blocks"] += not block_is_empty
    return statistics


def memory_accesses(output_folder: Path, input_file: Path) -> Dict[str, int]:
    """
    VGET, VSET and DUP-VSET of the reparation, summed over the repaired block lists (0 if the columns are missing)
    """
    repair_csv = output_folder.joinpath(f"repair_{input_file.stem}.csv")
    if not repair_csv.exists() or repair_csv.stat().st_size <= 1:
        return dict.fromkeys(MEMORY_ACCESSES, 0)
    repair_df = pd.read_csv(repair_csv)
    return {column: int(repair_df[column].sum()) if column in repair_df.columns else 0 for column in MEMORY_ACCESSES}


def parse_variant(value: str) -> Tuple[str, Path, str]:
    """
    Parses NAME=SRC[::FLAGS]
    """
    name, _, rest = value.partition("=")
    src_folder, _, flags = rest.partition("::")
    if not name or not src_folder:
        raise argparse.ArgumentTypeError(f"Variant must be NAME=SRC[::FLAGS]: {value}")
    return name, Path(src_folder).resolve(), flags


def keep_artifacts(output_folder: Path, artifact_file: Path) -> None:
    """
    Stores in a compressed archive the final bytecode of every contract (the CSVs grey writes in the output
    folder) and the assembly given to the importer (<contract>/<contract>_standard_json_output.json)
    """
    artifact_file.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(artifact_file, "w:gz") as archive:
        for csv_file in sorted(output_folder.glob("*.csv")):
            archive.add(csv_file, arcname=csv_file.name)
        for assembly_file in sorted(output_folder.glob("*/*_standard_json_output.json")):
            archive.add(assembly_file, arcname=str(assembly_file.relative_to(output_folder)))


def run_variant(src_folder: Path, input_info: Dict, output_folder: Path, flags: str, log_file: Path,
                artifact_file: Optional[Path] = None, timeout: Optional[float] = None) \
        -> Tuple[Optional[str], Dict, Dict[str, Dict[str, int]]]:
    """
    Runs grey once and returns the error, the metrics (including the memory accesses) and the bytecode
    statistics per contract. The artifacts are stored in artifact_file if given; the output folder is removed.
    A failure while collecting the results is reported as the error of this run, so the others are not lost
    """
    _, error = run_grey(src_folder, input_info, output_folder, flags, None, log_file, timeout)
    metrics, contract_statistics = {}, {}
    if error is None:
        try:
            metrics = {**collect_results(output_folder, input_info["source"]),
                       **memory_accesses(output_folder, input_info["source"])}
            contract_statistics = {contract: bytecode_statistics(code)
                                   for contract, code in grey_bytecodes(output_folder).items()}
            if artifact_file is not None:
                keep_artifacts(output_folder, artifact_file)
        except Exception as exception:
            error, metrics, contract_statistics = f"collecting results: {type(exception).__name__}: {exception}", {}, {}
    shutil.rmtree(output_folder, ignore_errors=True)
    return error, metrics, contract_statistics


def parse_reference(value: str) -> Tuple[str, Path]:
    """
    Parses NAME=PATH
    """
    name, _, path = value.partition("=")
    if not name or not path:
        raise argparse.ArgumentTypeError(f"Reference must be NAME=PATH: {value}")
    return name, Path(path).expanduser().resolve()


def solc_reference(input_info: Dict, solc_executable: Path,
                   artifact_file: Optional[Path] = None) -> Tuple[Dict[str, Optional[Dict[str, int]]], str]:
    """
    Bytecode statistics per contract generated by solc for the input (None for ambiguous names) and the
    compilation error. The bytecodes are stored in artifact_file (JSON) if given
    """
    # A failing compilation (e.g. a solc binary that cannot be executed) only loses the reference of this input
    try:
        codes, error = solc_bytecodes(input_info["source"], input_info["input_format"], str(solc_executable))
    except Exception as exception:
        return {}, f"{type(exception).__name__}: {exception}"
    if artifact_file is not None:
        artifact_file.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(artifact_file, "wt") as f:
            json.dump({"error": error, "bytecodes": codes}, f)
    return {contract: (bytecode_statistics(code) if code else None) for contract, code in codes.items()}, error


def print_summary(results: pd.DataFrame, contracts: pd.DataFrame, variant_names: List[str], depths: List[str],
                  reference_names: List[str]) -> None:
    reference = variant_names[0]
    for depth in depths:
        depth_rows = results[results["depth"] == int(depth)]
        failed_inputs = set(depth_rows[depth_rows["error"].notna()]["input"])
        ok_inputs = sorted(set(depth_rows["input"]) - failed_inputs)
        print(f"== depth {depth}: {depth_rows['input'].nunique()} inputs, succeeded in every variant: {len(ok_inputs)}")
        for variant in variant_names:
            new_errors = depth_rows[(depth_rows["variant"] == variant) & depth_rows["error"].notna()]
            reference_errors = set(depth_rows[(depth_rows["variant"] == reference) &
                                              depth_rows["error"].notna()]["input"])
            for _, row in new_errors[~new_errors["input"].isin(reference_errors)].iterrows():
                print(f"  new error [{variant}] {row['input']}: {row['error']}")

        ok_rows = depth_rows[depth_rows["input"].isin(ok_inputs)]
        by_variant = {variant: ok_rows[ok_rows["variant"] == variant].set_index("input") for variant in variant_names}
        header = f"  {'variant':24s} {'bytes':>9s} {'vs ref':>8s} {'b/w':>7s} {'vs prev':>8s} {'b/w':>7s} " \
                 f"{'slots':>6s} {'vs ref':>7s}"
        for reference_name in reference_names:
            header += f" {'gap ' + reference_name:>{max(9, len(reference_name) + 5)}s}"
        print(header)
        previous = None
        for variant in variant_names:
            current = by_variant[variant]
            line = f"  {variant:24s} {current['num_bytes'].sum():9.0f}"
            for other in [reference, previous]:
                if other is None or other == variant:
                    line += f" {'':>8s} {'':>7s}"
                    continue
                delta = current["num_bytes"] - by_variant[other]["num_bytes"]
                line += f" {delta.sum():+8.0f} {int((delta < 0).sum()):>3d}/{int((delta > 0).sum()):<3d}"
            slots_delta = current["memory_slots"].sum() - by_variant[reference]["memory_slots"].sum()
            line += f" {current['memory_slots'].sum():6.0f} {slots_delta:+7.0f}"
            for reference_name in reference_names:
                column = f"solc_{reference_name}_bytes"
                compared = contracts[(contracts["variant"] == variant) & (contracts["depth"] == int(depth)) &
                                     contracts["input"].isin(ok_inputs) & contracts[column].notna()]
                line += f" {(compared['grey_bytes'] - compared[column]).sum():+{max(9, len(reference_name) + 5)}.0f}"
            print(line)
            previous = variant
        for reference_name in reference_names:
            column = f"solc_{reference_name}_bytes"
            compared = contracts[(contracts["variant"] == reference) & (contracts["depth"] == int(depth)) &
                                 contracts["input"].isin(ok_inputs) & contracts[column].notna()]
            print(f"  ({reference_name}: {compared[column].sum():.0f} bytes over {len(compared)} contracts, "
                  f"{variant_names[0]} on them: {compared['grey_bytes'].sum():.0f})")

        # Bytecode statistics and memory accesses over the same inputs
        columns = [f"code_{statistic}" for statistic in BYTECODE_STATISTICS if statistic != "bytes"] + \
            MEMORY_ACCESSES + ["num_colors"]
        names = [column.replace("code_", "").replace("num_", "").replace("terminal_blocks", "terminal")
                 for column in columns]
        print(f"  {'statistics':24s} " + " ".join(f"{name:>9s}" for name in names))
        for variant in variant_names:
            print(f"  {variant:24s} " + " ".join(f"{by_variant[variant][column].sum():9.0f}" for column in columns))
        # Bytecode statistics next to each reference, over the contracts it compiles
        statistics = [statistic for statistic in BYTECODE_STATISTICS]
        for reference_name in reference_names:
            compared_contracts = contracts[(contracts["depth"] == int(depth)) & contracts["input"].isin(ok_inputs) &
                                           contracts[f"solc_{reference_name}_bytes"].notna()]
            print(f"  {'vs ' + reference_name:24s} " +
                  " ".join(f"{statistic.replace('terminal_blocks', 'terminal'):>9s}" for statistic in statistics))
            solc_rows = compared_contracts[compared_contracts["variant"] == reference]
            print(f"  {reference_name:24s} " +
                  " ".join(f"{solc_rows[f'solc_{reference_name}_{statistic}'].sum():9.0f}" for statistic in statistics))
            for variant in variant_names:
                variant_rows = compared_contracts[compared_contracts["variant"] == variant]
                print(f"  {variant:24s} " +
                      " ".join(f"{variant_rows[f'grey_{statistic}'].sum():9.0f}" for statistic in statistics))


def main():
    parser = argparse.ArgumentParser(description="Compare several variants of grey (src folder + flags)")
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("inputs", type=Path, nargs="*")
    parser.add_argument("--variant", type=parse_variant, action="append", dest="variants", required=True,
                        help="NAME=SRC[::FLAGS]; the first one is the reference")
    parser.add_argument("--from-workspace", type=Path, dest="workspace", default=None)
    parser.add_argument("--inputs-from", type=Path, dest="inputs_from", default=None,
                        help="File with one input path per line (added to the inputs given as arguments)")
    parser.add_argument("--depths", type=str, default="16,8", help="Comma-separated list of -d values")
    parser.add_argument("--flags", type=str, default=DEFAULT_FLAGS, help="Flags common to every variant")
    parser.add_argument("--solc", type=Path, default=REPO_ROOT.joinpath("examples/solc-without-opt"))
    parser.add_argument("--force-solc", type=Path, dest="force_solc", default=None,
                        help="solc binary used for every input, instead of the one configured in the workspace")
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--solc-reference", action="store_true", dest="solc_reference",
                        help="Compile every input with its own solc and report the gap of each variant")
    parser.add_argument("--timeout", type=float, default=None,
                        help="Seconds after which a grey run (and the solc processes it started) is killed")
    parser.add_argument("--keep-artifacts", action="store_true", dest="keep_artifacts",
                        help="Store the final bytecode and the importer's assembly of every run in "
                             "<output_dir>/artifacts/<variant>/<run>.tar.gz and solc's bytecodes in "
                             "<output_dir>/artifacts/solc_<reference>/<input>.json.gz")
    parser.add_argument("--reference-solc", type=parse_reference, action="append", dest="reference_solcs",
                        default=[], help="NAME=PATH of another solc binary used as a reference (repeatable)")
    args = parser.parse_args()

    solc_executable = args.solc.resolve()
    input_files = list(args.inputs)
    if args.inputs_from is not None:
        input_files += [Path(line.strip()) for line in args.inputs_from.read_text().splitlines() if line.strip()]
    inputs = [{"source": input_file.resolve(), "input_format": input_format_from_extension(input_file),
               "solc": solc_executable, "contract": None} for input_file in input_files]
    if args.workspace is not None:
        workspace_inputs, skipped = inputs_from_workspace(args.workspace, solc_executable)
        inputs.extend(workspace_inputs)
        for skipped_entry in skipped:
            print(f"Skipped (not a file): {skipped_entry}")
    if args.force_solc is not None:
        # The same source configured with several binaries becomes a single input
        forced_solc, unique_inputs = args.force_solc.resolve(), dict()
        for input_info in inputs:
            input_info["solc"] = forced_solc
            unique_inputs.setdefault(run_identifier(input_info), input_info)
        inputs = list(unique_inputs.values())
    depths = [depth.strip() for depth in args.depths.split(",")]
    output_dir = args.output_dir.resolve()
    variant_names = [name for name, _, _ in args.variants]
    assert len(set(variant_names)) == len(variant_names), "Variant names must be unique"

    # None: the input's own solc
    references: List[Tuple[str, Optional[Path]]] = ([("solc", None)] if args.solc_reference else []) + \
        args.reference_solcs
    reference_names = [name for name, _ in references]
    assert len(set(reference_names)) == len(reference_names), "Reference names must be unique"

    tasks, solc_tasks = {}, {}
    with ProcessPoolExecutor(max_workers=args.jobs) as executor:
        for reference_name, reference_path in references:
            for input_info in inputs:
                artifact_file = output_dir.joinpath("artifacts", f"solc_{reference_name}",
                                                    f"{run_identifier(input_info)}.json.gz") \
                    if args.keep_artifacts else None
                solc_tasks[(reference_name, run_identifier(input_info))] = executor.submit(
                    solc_reference, input_info, reference_path or input_info["solc"], artifact_file)
        for name, src_folder, variant_flags in args.variants:
            for input_info in inputs:
                for depth in depths:
                    run_name = f"{run_identifier(input_info)}_d{depth}"
                    output_folder = output_dir.joinpath("runs", name, run_name)
                    log_file = output_dir.joinpath("logs", name, f"{run_name}.txt")
                    flags = f"{args.flags} {variant_flags} -d {depth}"
                    artifact_file = output_dir.joinpath("artifacts", name, f"{run_name}.tar.gz") \
                        if args.keep_artifacts else None
                    tasks[(name, run_identifier(input_info), depth)] = executor.submit(
                        run_variant, src_folder, input_info, output_folder, flags, log_file, artifact_file,
                        args.timeout)

    # The results of grey are stored first, so that they are not lost if something fails afterwards
    rows, grey_contract_statistics = [], []
    for (name, input_id, depth), task in tasks.items():
        error, metrics, contract_statistics = task.result()
        code_totals = {f"code_{statistic}": sum(statistics[statistic] for statistics in contract_statistics.values())
                       for statistic in BYTECODE_STATISTICS} if error is None else {}
        rows.append({"variant": name, "input": input_id, "depth": int(depth), "error": error, **metrics,
                     **code_totals})
        grey_contract_statistics.append((name, input_id, depth, contract_statistics))
    results = pd.DataFrame(rows, columns=["variant", "input", "depth", "error", *METRICS, *MEMORY_ACCESSES,
                                          *[f"code_{statistic}" for statistic in BYTECODE_STATISTICS]])
    results.to_csv(output_dir.joinpath("results.csv"), index=False)

    solc_statistics = {}
    for (reference_name, input_id), task in solc_tasks.items():
        solc_statistics[(reference_name, input_id)], solc_error = task.result()
        if solc_error:
            print(f"{reference_name} reference of {input_id}: {solc_error[:200]}")
    contract_rows = []
    for name, input_id, depth, contract_statistics in grey_contract_statistics:
        for contract, statistics in sorted(contract_statistics.items()):
            row = {"variant": name, "input": input_id, "depth": int(depth), "contract": contract,
                   **{f"grey_{statistic}": statistics[statistic] for statistic in BYTECODE_STATISTICS}}
            for reference_name in reference_names:
                reference_statistics = solc_statistics.get((reference_name, input_id), {}).get(contract) or {}
                row.update({f"solc_{reference_name}_{statistic}": reference_statistics.get(statistic)
                            for statistic in BYTECODE_STATISTICS})
            contract_rows.append(row)
    contracts = pd.DataFrame(contract_rows, columns=[
        "variant", "input", "depth", "contract", *[f"grey_{statistic}" for statistic in BYTECODE_STATISTICS],
        *[f"solc_{name}_{statistic}" for name in reference_names for statistic in BYTECODE_STATISTICS]])
    contracts.to_csv(output_dir.joinpath("contracts.csv"), index=False, quoting=csv.QUOTE_MINIMAL)
    print(f"Inputs: {len(inputs)} x depths {depths} x variants {variant_names}")
    print_summary(results, contracts, variant_names, depths, reference_names)


if __name__ == "__main__":
    main()
