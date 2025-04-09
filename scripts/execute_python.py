import os
import subprocess
import shutil
import filecmp
import json
from typing import List, Dict, Any
from pathlib import Path
import multiprocessing as mp
import sys
import pandas as pd
from count_num_ins import instrs_from_opcodes
from compare_outputs import compare_files_removing_failed_tests


def combine_dfs(csv_folder: Path, combined_csv: Path):
    dfs = []
    for csv_file in csv_folder.glob("*.csv"):
        df = pd.read_csv(csv_file, index_col=0)
        df.reset_index(drop=True, inplace=True)
        dfs.append(df)
    combined_df = pd.concat(dfs, ignore_index=True)
    combined_df.to_csv(combined_csv)


def extract_contract_name(original_test: str) -> str:
    with open(original_test, 'r') as f:
        return list(json.load(f).values())[0]["contract"].split(":")[-1]


def filter_row(list_of_rows: List[Dict[str, Any]], row_name, yul_file) -> Dict[str, Any]:
    matching_rows = [row for row in list_of_rows if row["name"].strip() == row_name]
    if len(matching_rows) != 1:
        print("ERROR FILTERING", yul_file, row_name, len(matching_rows), [row["name"] for row in list_of_rows])
    return matching_rows[0]


def execute_yul_test(yul_file: str, csv_folder: Path) -> None:
    yul_file = str(yul_file)
    yul_dir = os.path.dirname(yul_file)
    yul_base = os.path.basename(yul_file).replace("_standard_input.json", "")

    print(f"Procesando archivo: {yul_file}")

    # Run external commands
    solc_command = [
        "./solc-latest",
        yul_file,
        "--standard-json",
    ]
    output_file = os.path.join(yul_dir, f"{yul_base}.output")
    with open(output_file, "w") as output:
        subprocess.run(solc_command, stdout=output)

    grey_command = [
        "python3",
        "src/grey_main.py",
        "-s", yul_file,
        "-g", "-v",
        "-if", "standard-json",
        "-solc", "./solc-latest",
        "-o", f"/tmp/{yul_base}",
    ]
    log_file = os.path.join(yul_dir, f"{yul_base}.log")
    # with open(log_file, "w") as log:
    #     subprocess.run(grey_command, stdout=log)
    # print(yul_file)
    subprocess.run(grey_command)
    
    print(" ".join(grey_command))

    # Copy results
    tmp_dir = f"/tmp/{yul_base}"
    if os.path.isdir(tmp_dir):
        for asm_file in Path(tmp_dir).rglob("*_asm.json"):
            shutil.copy(str(asm_file), yul_dir)

    test_file = os.path.join(yul_dir, "test")
    csv_name = f"{Path(Path(yul_file).parent).stem}:{yul_base}.csv"
    print("CSV NAME", csv_name)

    if os.path.isfile(test_file):
        replace_command = [
            "python3",
            "scripts/replace_bytecode_test.py",
            test_file,
            log_file,
        ]
        subprocess.run(replace_command)
        # print(" ".join(replace_command))
        result_original = os.path.join(yul_dir, "resultOriginal.json")

        testrunner_command_original = [
            "/system/experiments/Systems/solidity/build/test/tools/testrunner",
            "/system/experiments/Systems/evmone_ahernandez/build/lib/libevmone.so",
            test_file,
            result_original
        ]
        subprocess.run(testrunner_command_original)
        
        # We extract the corresponding contract name from the test file
        analyzed_contract = extract_contract_name(test_file)
        test_grey_file = f"{yul_dir}/test_grey"
        result_grey = os.path.join(yul_dir, "resultGrey.json")

        testrunner_command_grey = [
            "/system/experiments/Systems/solidity/build/test/tools/testrunner",
            "/system/experiments/Systems/evmone_ahernandez/build/lib/libevmone.so",     
            test_grey_file,
            result_grey
        ]
        # print(' '.join(testrunner_command_grey))
        subprocess.run(testrunner_command_grey)

        # We need to compare them dropping the gas usage
        file_comparison, gas_original, gas_grey = compare_files_removing_failed_tests(result_original, test_file, result_grey, test_grey_file)
        # If file_comparison is empty, it means that the match is precise
        if file_comparison == 0:
            print("[RES]: Test passed.")
            result_dict = instrs_from_opcodes(output_file, log_file)
            csv_file = csv_folder.joinpath("correctos").joinpath(csv_name)
            if len(result_dict) > 0:
                filtered_row = filter_row(result_dict, analyzed_contract, yul_file)
                filtered_row["gas_original"] = gas_original
                filtered_row["gas_grey"] = gas_grey
                pd.DataFrame([filtered_row]).to_csv(csv_file)
            else:
                pd.DataFrame(result_dict).to_csv(csv_file)
        else:
            csv_file = csv_folder.joinpath("fallan").joinpath(csv_name)
            pd.DataFrame([{"archivo": yul_base}]).to_csv(csv_file)
            print(f"[RES]: Test failed. {yul_file}")
    else:
        csv_file = csv_folder.joinpath("no_test").joinpath(csv_name)
        pd.DataFrame([{"archivo": yul_base}]).to_csv(csv_file)
        print("Test not found")


def run_experiments(n_cpus):
    # Change the directory to the root

    os.chdir("..")
    # DIRECTORIO_TESTS = "examples/test/semanticTests"
    # DIRECTORIO_TESTS = "tests_evmone"
    DIRECTORIO_TESTS = "modifiedTests/"
    CSV_FOLDER = Path("csvs")
    CSV_FOLDER.mkdir(exist_ok=True, parents=True)
    CSV_FOLDER.joinpath("correctos").mkdir(exist_ok=True, parents=True)
    CSV_FOLDER.joinpath("fallan").mkdir(exist_ok=True, parents=True)
    CSV_FOLDER.joinpath("no_test").mkdir(exist_ok=True, parents=True)
    
    # Check if the directory exists
    if not os.path.isdir(DIRECTORIO_TESTS):
        print(f"El directorio {DIRECTORIO_TESTS} no existe.")
        exit(1)

    # Find all files matching "*standard_input.json" in the directory
    yul_files = list(Path(DIRECTORIO_TESTS).rglob("*standard_input.json"))
    with mp.Pool(n_cpus) as p:
        p.starmap(execute_yul_test, [[file_, CSV_FOLDER] for file_ in yul_files])
    print("Procesamiento completado.")
    # combine_dfs(CSV_FOLDER, Path("combined.csv"))


if __name__ == "__main__":
    if len(sys.argv) == 2:
        n_cpus = int(sys.argv[1])
    else:
        n_cpus = max(mp.cpu_count() - 1, 1)
    run_experiments(n_cpus)
