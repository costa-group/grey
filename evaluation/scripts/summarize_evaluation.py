#!/usr/bin/env python3
"""
Final results of one evaluation run (evaluate.sh), from its local results folder
(evaluation/data/mainnet/results/<RESULTS_NAME>):
  - the configuration (compile_settings.txt);
  - bytecode size, grey vs solc, on the 1,000 contracts and on the semantic tests (the compilation logs);
  - mainnet transactions: the receipt check, the gas of grey vs solc over the transactions where both match the
    original (summary.txt), the classes of the mismatches and where every sampled transaction goes (diagnosis/);
  - semantic tests: the test classes (grey failing where solc passes is a bug) and the gas (semantic/summary_d*.txt).
The summary is printed and written to final_results.txt in the same folder.

Usage: python3 evaluation/scripts/summarize_evaluation.py <results folder>
"""
import re
import sys
from pathlib import Path

import pandas as pd

BYTES_PATTERN = re.compile(r"\(solc: (\d+) bytes over (\d+) contracts, grey on them: (\d+)\)")
DEPTH_PATTERN = re.compile(r"== depth (\d+): (\d+) inputs, succeeded in every variant: (\d+)")


def bytecode_size(log_file: Path) -> list:
    """
    Lines with the size of grey's and solc's creation code per depth, over the contracts that both compile
    """
    if not log_file.is_file():
        return [f"  (no compilation log: {log_file.name})"]
    lines, depth = [], None
    for line in log_file.read_text().splitlines():
        header = DEPTH_PATTERN.search(line)
        if header:
            depth = header.groups()
            continue
        sizes = BYTES_PATTERN.search(line)
        if sizes and depth:
            solc, contracts, grey = (int(value) for value in sizes.groups())
            lines.append(f"  depth {depth[0]}: {depth[2]}/{depth[1]} inputs compiled by both; over {contracts} contracts, "
                         f"grey {grey:,} B vs solc {solc:,} B: {grey - solc:+,} B ({100 * (grey - solc) / solc:+.2f}%)")
            depth = None
    return lines or ["  (no size table in the log)"]


def mainnet(results: Path) -> list:
    lines = []
    summary = results / "summary.txt"
    if not summary.is_file():
        return ["  (no replay results)"]
    for line in summary.read_text().splitlines():
        if line.startswith("Offline replay") or "receipt check" in line or line.startswith("over ") or " vs " in line:
            lines.append("  " + line.strip())
    accounting = results / "diagnosis" / "accounting.txt"
    diagnosis = results / "diagnosis" / "transactions.csv"
    if diagnosis.is_file():
        classes = pd.read_csv(diagnosis)
        # Legitimate: gas- or code-dependent (they appear with any recompilation), or the same as the reference. Anything
        # else (UNEXPLAINED, or a status change that neither explains) is a possible bug of the variant
        legitimate = classes["class"].str.startswith(("gas", "code", "same as", "error"))
        unexplained = classes[~legitimate]
        for variant, rows in classes.groupby("variant"):
            counts = rows["class"].str.split(" ").str[0].value_counts()
            lines.append(f"  mismatches of {variant} with the original, by class: "
                         + ", ".join(f"{kind} {count}" for kind, count in counts.items()))
        lines.append(f"  unexplained mismatches (possible bugs to investigate): {len(unexplained)}")
        for (variant, address), rows in unexplained.groupby(["variant", "address"]):
            lines.append(f"    {variant} {address}: {len(rows)} transactions ({', '.join(rows['class'].unique())})")
    if accounting.is_file():
        lines.append("  where every sampled transaction goes:")
        lines += ["    " + line for line in accounting.read_text().splitlines()]
    return lines


def semantic(results: Path) -> list:
    folder = results / "semantic"
    summaries = sorted(folder.glob("summary_d*.txt"), key=lambda path: -int(path.stem.split("_d")[1]))
    if not summaries:
        return ["  (no semantic test results)"]
    lines = []
    for summary in summaries:
        text = summary.read_text()
        failing = re.search(r"variant_fails (\d+)", text)
        lines.append(f"  depth {summary.stem.split('_d')[1]}: grey fails where solc passes (a bug): "
                     f"{failing.group(1) if failing else 0} tests")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith(("grey vs solc:", "constructor", "call ")) or "variant_fails" in stripped:
                lines.append("    " + stripped)
    return lines


def main():
    results = Path(sys.argv[1])
    settings = results / "compile_settings.txt"
    report = ["== Configuration"]
    report += ["  " + line for line in settings.read_text().splitlines()] if settings.is_file() else ["  (unknown)"]
    report += ["", "== Bytecode size (creation code), 1,000 most-called contracts"] + bytecode_size(results / "compile_bytes.txt")
    report += ["", "== Bytecode size (creation code), semantic tests"] + bytecode_size(results / "semantic" / "compile_bytes.txt")
    report += ["", "== Mainnet transactions (gas = transaction gasUsed, Prague, block gas limit)"] + mainnet(results)
    report += ["", "== Semantic tests (testrunner on evmone; gas without the intrinsic cost)"] + semantic(results)
    text = "\n".join(report)
    results.joinpath("final_results.txt").write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
