#!/usr/bin/env python3
"""
Gas and correctness of grey vs solc on the semantic tests, executed with the testrunner of solidity's branch
testExpectationExtraction (built by evaluation/scripts/build_testrunner.sh) on evmone.

Each input of the corpus (corpus/semanticTests/<name>/<name>_standard_input.json) has next to it the trace of its
test (`test`: bytecode, contract and the constructor/call entries with calldata, value and expected
status/returndata). For every variant, the bytecode of the trace is replaced by the variant's creation code of the
test's contract (taken from the artifacts of `compare_variants.py --keep-artifacts`) and testrunner is executed.
testrunner checks status and returndata against the trace and records, per entry, the message ("Passed.",
"Creation succeeded.", "Expected ..."), gasUsed (execution gas of the message minus the capped refund, without the
21000 + calldata intrinsic) and gasUsedForDeposit (code deposit, 200 per byte). With
evaluation/scripts/testrunner_logs.patch it also records a digest of the logs of the entry and of the whole storage after
it, which are compared with the reference variant (the first one). When a variant only fails because it returns
memory addresses that moved with its initial free memory pointer (the memory slots of grey's reparation are reserved
below it), the test is executed again expecting the shifted addresses and, if it then passes, it is classified as
memory_layout_differs instead of variant_fails (e.g. strings.sol's toSlice at d8: 0xe0 instead of 0xa0).

Usage (from ~/grey_eval on grey-remote):
    python3 evaluation/scripts/gas_semantic_tests.py results/thread_semantic --inputs-from inputs_semantic.txt \
        --solc bin/solc-0.8.35 --variant solc=solc_solc --variant grey=thread \
        --testrunner gas/build/solidity/build/test/tools/testrunner \
        --evmone gas/build/evmone-94582ffd/build/lib/libevmone.so --out-dir gas/semantic [--jobs N]
A variant named TRACE (e.g. --variant trace=TRACE) keeps the trace's own bytecode (solc 0.8.29 of the extraction).

Outputs in --out-dir: entries.csv.gz (one row per test, entry and variant) and summary.txt.
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from gas_common import (NotEnoughDiskSpace, ensure_free_space, input_info_for, intrinsic_calldata_gas, jobs_from_load,
                        variant_creation_codes)
from compare_repair_slots import run_identifier

PASSING_MESSAGES = {"Passed.", "Creation succeeded."}
OUTPUT_MISMATCH = "Expected different output."
TRACE_VARIANT = "TRACE"


def parse_variant(value: str) -> Tuple[str, str]:
    name, _, artifact_name = value.partition("=")
    if not name or not artifact_name:
        raise argparse.ArgumentTypeError(f"Variant must be NAME=ARTIFACT_FOLDER: {value}")
    return name, artifact_name


def free_memory_pointer_initialisations(code: bytes) -> List[int]:
    """
    Values stored as the initial free memory pointer in the code (PUSHn X; [DUP1;] PUSH1 0x40; MSTORE, X >= 0x80),
    in order: the one of the constructor and the one of the runtime, plus those of the nested objects. The code is
    disassembled linearly, so the data after the code may add spurious candidates (harmless, they are only tried)
    """
    instructions, position = [], 0
    while position < len(code):
        opcode = code[position]
        push_size = opcode - 0x5f if 0x60 <= opcode <= 0x7f else 0
        instructions.append((opcode, int.from_bytes(code[position + 1:position + 1 + push_size], "big")))
        position += 1 + push_size
    # The constructors of via-IR code keep a copy of the pointer: PUSHn X; DUP1; PUSH1 0x40; MSTORE
    values = []
    for index, (opcode, value) in enumerate(instructions):
        if not (0x60 <= opcode <= 0x7f and value >= 0x80):
            continue
        following = instructions[index + 1:index + 4]
        if following and following[0][0] == 0x80:
            following = following[1:]
        if len(following) >= 2 and following[0] == (0x60, 0x40) and following[1][0] == 0x52:
            values.append(value)
    return values


def candidate_pointer_shifts(reference_code: bytes, variant_code: bytes) -> List[int]:
    """
    Differences between the initial free memory pointers of the variant and of the reference (e.g. +0x40 when grey
    reserves two memory slots for the reparation), smallest in absolute value first
    """
    reference_values = free_memory_pointer_initialisations(reference_code)
    variant_values = free_memory_pointer_initialisations(variant_code)
    shifts = {variant_value - reference_value for variant_value in variant_values for reference_value in
              reference_values if variant_value != reference_value}
    return sorted(shifts, key=lambda shift: (abs(shift), shift))


def shift_pointer_words(returndata: str, shift: int, lowest_pointer: int) -> str:
    """
    Returndata (hex) whose 32-byte words that look like memory pointers (lowest_pointer <= word < 2^32) are shifted.
    The trailing bytes that do not form a whole word are kept
    """
    words = [returndata[start:start + 64] for start in range(0, len(returndata) - len(returndata) % 64, 64)]
    shifted = []
    for word in words:
        value = int(word, 16)
        if lowest_pointer <= value < 2 ** 32 and value + shift >= 0:
            value += shift
        shifted.append(f"{value:064x}")
    return "".join(shifted) + returndata[len(words) * 64:]


def run_testrunner(testrunner: Path, evmone: Path, trace: Dict, work_folder: Path, name: str, timeout: float) \
        -> Tuple[Optional[List[Dict]], str]:
    """
    Executes testrunner on a trace with a single test and returns its recorded entries (None if it crashed or
    timed out) and the error
    """
    trace_file, result_file = work_folder.joinpath(f"{name}.json"), work_folder.joinpath(f"{name}_result.json")
    trace_file.write_text(json.dumps(trace))
    try:
        subprocess.run([str(testrunner), str(evmone), str(trace_file), str(result_file)], capture_output=True,
                       timeout=timeout, cwd=work_folder)
    except subprocess.TimeoutExpired:
        return None, "timeout"
    if not result_file.is_file():
        return None, "no result file (crash)"
    results = json.loads(result_file.read_text())
    return (next(iter(results.values())) if results else []), ""


def evaluate_input(source: Path, solc_executable: Path, artifacts_dir: Path, variants: List[Tuple[str, str]],
                   testrunner: Path, evmone: Path, depth: int, timeout: float) -> List[Dict]:
    """
    Rows (one per entry of the test and variant) for one input of the corpus. A variant without code for the
    test's contract gets a single row with its error
    """
    test_file = source.parent.joinpath("test")
    if not test_file.is_file():
        return [{"input": source.parent.name, "variant": name, "error": "no test trace"} for name, _ in variants]
    test_key, test_data = next(iter(json.loads(test_file.read_text()).items()))
    contract = test_data["contract"].split(":")[-1]
    input_info = input_info_for(source, solc_executable)
    identifier = run_identifier(input_info)
    rows, codes = [], dict()
    with tempfile.TemporaryDirectory(prefix="gas_semantic_") as work_folder:
        for name, artifact_name in variants:
            base_row = {"input": identifier, "test": test_key, "contract": contract, "variant": name}
            if artifact_name == TRACE_VARIANT:
                code = test_data["bytecode"]
            else:
                variant_codes = variant_creation_codes(artifacts_dir, artifact_name, input_info, depth)
                code = None if variant_codes is None else variant_codes.get(contract)
                if code is None:
                    error = "no artifact (run failed)" if variant_codes is None else "no code for the test's contract"
                    rows.append({**base_row, "error": error})
                    continue
            if "__$" in code:
                rows.append({**base_row, "error": "unlinked library placeholders"})
                continue
            entries, error = run_testrunner(testrunner, evmone, {test_key: {**test_data, "bytecode": code}},
                                            Path(work_folder), name, timeout)
            if entries is None:
                rows.append({**base_row, "error": error})
                continue
            codes[name] = code
            code_bytes = bytes.fromhex(code)
            for index, (test_entry, result) in enumerate(zip(test_data["tests"], entries)):
                is_creation = test_entry["kind"] == "constructor"
                calldata = bytes.fromhex(test_entry["input"]["calldata"])
                rows.append({**base_row, "entry": index, "kind": test_entry["kind"], "message": result["message"],
                             "passed": result["message"] in PASSING_MESSAGES,
                             "gas_used": int(result["gasUsed"]), "gas_deposit": int(result["gasUsedForDeposit"]),
                             "logs": result.get("logs", ""), "storage": result.get("storage", ""),
                             "calldata_gas": intrinsic_calldata_gas((code_bytes if is_creation else b"") + calldata,
                                                                    is_creation),
                             "code_bytes": len(code_bytes), "pointer_shift": "", "error": ""})
            if len(entries) != len(test_data["tests"]):
                rows.append({**base_row, "error": f"{len(entries)} results for {len(test_data['tests'])} entries"})

        mark_pointer_shifts(rows, codes, test_key, test_data, variants[0][0], testrunner, evmone, Path(work_folder),
                            timeout)
    return rows


def mark_pointer_shifts(rows: List[Dict], codes: Dict[str, str], test_key: str, test_data: Dict, reference: str,
                        testrunner: Path, evmone: Path, work_folder: Path, timeout: float) -> None:
    """
    A variant may return a different value only because it starts its free memory pointer elsewhere (grey reserves
    the memory slots of the reparation below it, so every allocation moves up): the test then expects a memory
    address of the reference, e.g. a slice (length, pointer). When the reference passes every entry and the variant
    only fails with "Expected different output.", the variant is executed again expecting the reference's returndata
    of those entries with its pointer-like words shifted by the difference of the initial free memory pointers. If
    every entry then passes, pointer_shift (e.g. "+0x40") is stored in the variant's rows; the test is classified as
    memory_layout_differs instead of variant_fails
    """
    reference_rows = [row for row in rows if row["variant"] == reference]
    if reference not in codes or not reference_rows or not all(row.get("passed") for row in reference_rows):
        return
    reference_code = bytes.fromhex(codes[reference])
    lowest_pointer = min(free_memory_pointer_initialisations(reference_code), default=0x80)
    for name, code in codes.items():
        variant_rows = [row for row in rows if row["variant"] == name]
        failing = [row for row in variant_rows if not row.get("passed")]
        if name == reference or not failing or any(row.get("message") != OUTPUT_MISMATCH for row in failing):
            continue
        failing_entries = {row["entry"] for row in failing}
        for shift in candidate_pointer_shifts(reference_code, bytes.fromhex(code)):
            shifted_tests = []
            for index, test_entry in enumerate(test_data["tests"]):
                if index in failing_entries:
                    output = test_entry["output"]
                    test_entry = {**test_entry, "output": {**output, "returndata": shift_pointer_words(
                        output["returndata"], shift, lowest_pointer)}}
                shifted_tests.append(test_entry)
            entries, _ = run_testrunner(testrunner, evmone,
                                        {test_key: {**test_data, "tests": shifted_tests, "bytecode": code}},
                                        work_folder, f"{name}_shift", timeout)
            if entries is not None and len(entries) == len(shifted_tests) and \
                    all(result["message"] in PASSING_MESSAGES for result in entries):
                for row in variant_rows:
                    row["pointer_shift"] = f"{shift:+#x}"
                break


def classify_tests(entries: pd.DataFrame, reference: str, variants: List[str]) -> pd.DataFrame:
    """
    One row per test and non-reference variant with its class:
      - excluded: the reference does not pass every entry (environment-dependent test) or has no code;
      - variant_error: the variant has no code or testrunner failed;
      - memory_layout_differs: the variant only fails because some returned values are memory addresses, which move
        with its initial free memory pointer (see mark_pointer_shifts); not a correctness bug, but excluded from gas;
      - variant_fails: the reference passes every entry and the variant does not (a correctness bug);
      - side_effects_differ: both pass, but the digest of the logs or of the storage differs at some entry;
      - included: both pass with the same side effects (used for the gas comparison)
    """
    classes = []
    for test, test_rows in entries.groupby("test", sort=True):
        reference_rows = test_rows[test_rows.variant == reference]
        reference_ok = (reference_rows.error == "").all() and len(reference_rows) > 0 and reference_rows.passed.all()
        for variant in variants:
            if variant == reference:
                continue
            variant_rows = test_rows[test_rows.variant == variant]
            if not reference_ok:
                test_class, detail = "excluded", "reference fails or has no code"
            elif len(variant_rows) == 0 or (variant_rows.error != "").any():
                test_class, detail = "variant_error", "; ".join(sorted(set(variant_rows.error)))
            elif not variant_rows.passed.all() and (variant_rows.pointer_shift != "").all():
                failing = variant_rows[~variant_rows.passed]
                test_class, detail = "memory_layout_differs", \
                    f"entries {', '.join(str(int(entry)) for entry in failing.entry)}: pointers shifted by " \
                    f"{failing.iloc[0].pointer_shift}"
            elif not variant_rows.passed.all():
                failing = variant_rows[~variant_rows.passed].iloc[0]
                test_class, detail = "variant_fails", f"entry {int(failing.entry)}: {failing.message}"
            else:
                merged = reference_rows.merge(variant_rows, on="entry", suffixes=("_reference", "_variant"))
                differing = merged[(merged.logs_reference != merged.logs_variant) |
                                   (merged.storage_reference != merged.storage_variant)]
                if len(differing) > 0:
                    test_class, detail = "side_effects_differ", f"entry {int(differing.iloc[0].entry)}"
                else:
                    test_class, detail = "included", ""
            classes.append({"test": test, "variant": variant, "class": test_class, "detail": detail})
    return pd.DataFrame(classes)


def gas_summary(entries: pd.DataFrame, reference: str, variant: str, tests: List[str]) -> List[str]:
    """
    Gas of the variant vs the reference over the given tests (creation and calls), as lines of text
    """
    selected = entries[entries.test.isin(tests) & entries.variant.isin([reference, variant]) & (entries.error == "")]
    pivot = selected.pivot_table(index=["test", "entry", "kind"], columns="variant",
                                 values=["gas_used", "gas_deposit", "calldata_gas"], aggfunc="first")
    lines = []
    for kind in ["constructor", "call"]:
        if kind not in pivot.index.get_level_values("kind"):
            continue
        kind_rows = pivot.xs(kind, level="kind")
        measures = [("gas_used", kind_rows["gas_used"])]
        if kind == "constructor":
            measures += [("without deposit", kind_rows["gas_used"] - kind_rows["gas_deposit"]),
                         ("deposit", kind_rows["gas_deposit"]),
                         ("+ initcode calldata", kind_rows["gas_used"] + kind_rows["calldata_gas"])]
        for label, values in measures:
            reference_total, variant_total = int(values[reference].sum()), int(values[variant].sum())
            difference = variant_total - reference_total
            percentage = 100 * difference / reference_total if reference_total else 0.0
            per_entry = values[variant] - values[reference]
            lines.append(f"  {kind:<11} {label:<20} {reference}: {reference_total:>13,}  {variant}: "
                         f"{variant_total:>13,}  diff {difference:>+11,} ({percentage:+.3f}%)  better / worse / equal "
                         f"{(per_entry < 0).sum()} / {(per_entry > 0).sum()} / {(per_entry == 0).sum()}")
    if "call" not in pivot.index.get_level_values("kind"):
        return lines
    calls = pivot.xs("call", level="kind")["gas_used"]
    regressions = (calls[variant] - calls[reference]).sort_values(ascending=False)
    regressions = regressions[regressions > 0].head(20)
    if len(regressions) > 0:
        lines.append(f"  largest call regressions ({variant} - {reference}):")
        for (test, entry), difference in regressions.items():
            lines.append(f"    {int(difference):>+8,}  ({int(calls.loc[(test, entry), reference]):,} -> "
                         f"{int(calls.loc[(test, entry), variant]):,})  {test} entry {int(entry)}")
    return lines


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("results_dir", type=Path, help="Output folder of compare_variants.py --keep-artifacts")
    parser.add_argument("--inputs-from", type=Path, dest="inputs_from", required=True,
                        help="The inputs file given to compare_variants.py (paths relative to the current folder)")
    parser.add_argument("--solc", type=Path, required=True, help="The binary given to compare_variants.py --force-solc")
    parser.add_argument("--variant", type=parse_variant, action="append", dest="variants", required=True,
                        help="NAME=ARTIFACT_FOLDER (grey variant or solc_<reference>; TRACE for the trace's own "
                             "bytecode). The first one is the reference")
    parser.add_argument("--testrunner", type=Path, required=True)
    parser.add_argument("--evmone", type=Path, required=True, help="libevmone.so (EVMC ABI 12)")
    parser.add_argument("--out-dir", type=Path, dest="out_dir", required=True)
    parser.add_argument("--depth", type=int, default=16)
    parser.add_argument("--jobs", type=int, default=None, help="Default: free cores given the load, minus 3")
    parser.add_argument("--timeout", type=float, default=600, help="Seconds per testrunner execution")
    parser.add_argument("--min-free-gb", type=float, dest="min_free_gb", default=50)
    parser.add_argument("--limit", type=int, default=None, help="Only the first N inputs (pilot runs)")
    args = parser.parse_args()

    sources = [Path(line.strip()) for line in args.inputs_from.read_text().splitlines() if line.strip()]
    sources = sources[:args.limit] if args.limit else sources
    jobs = args.jobs or jobs_from_load()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    ensure_free_space(args.out_dir, args.min_free_gb)
    ensure_free_space(Path(tempfile.gettempdir()), args.min_free_gb)
    print(f"{len(sources)} inputs, {jobs} jobs", flush=True)

    artifacts_dir = args.results_dir.joinpath("artifacts")
    rows: List[Dict] = []
    with ProcessPoolExecutor(max_workers=jobs) as executor:
        futures = [executor.submit(evaluate_input, source, args.solc, artifacts_dir, args.variants,
                                   args.testrunner.resolve(), args.evmone.resolve(), args.depth, args.timeout)
                   for source in sources]
        for index, future in enumerate(futures, 1):
            rows.extend(future.result())
            if index % 100 == 0:
                print(f"{index} / {len(sources)}", flush=True)
                try:
                    ensure_free_space(args.out_dir, args.min_free_gb)
                except NotEnoughDiskSpace as exception:
                    print(f"Stopping: {exception}", flush=True)
                    for pending in futures:
                        pending.cancel()
                    break

    entries = pd.DataFrame(rows)
    entries["error"] = entries["error"].fillna("")
    # Rows of errors (no code, crash) have no entry: they never pass
    entries["passed"] = entries["passed"].fillna(False).astype(bool)
    entries["pointer_shift"] = entries["pointer_shift"].fillna("") if "pointer_shift" in entries else ""
    entries.to_csv(args.out_dir.joinpath("entries.csv.gz"), index=False)
    variant_names = [name for name, _ in args.variants]
    reference = variant_names[0]
    classes = classify_tests(entries, reference, variant_names)
    classes.to_csv(args.out_dir.joinpath("tests.csv"), index=False)

    lines = [f"Semantic tests: {entries.test.nunique()} tests with a trace; reference {reference}; "
             f"testrunner {args.testrunner}; evmone {args.evmone}"]
    for variant in variant_names[1:]:
        variant_classes = classes[classes.variant == variant]
        lines.append(f"\n{variant} vs {reference}: " + ", ".join(
            f"{test_class} {count}" for test_class, count in variant_classes["class"].value_counts().items()))
        for _, row in variant_classes[variant_classes["class"].isin(["variant_fails", "memory_layout_differs",
                                                                      "side_effects_differ", "variant_error"])].iterrows():
            lines.append(f"  {row['class']}: {row.test} ({row.detail})")
        included = variant_classes[variant_classes["class"] == "included"].test.tolist()
        lines.append(f" gas over the {len(included)} included tests:")
        lines.extend(gas_summary(entries, reference, variant, included))
    summary = "\n".join(lines)
    args.out_dir.joinpath("summary.txt").write_text(summary + "\n")
    print(summary)


if __name__ == "__main__":
    main()
