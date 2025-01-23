import os
import subprocess
import shutil
import filecmp
from pathlib import Path
import multiprocessing as mp
import sys


def execute_yul_test(yul_file: str) -> None:
    yul_file = str(yul_file)
    yul_dir = os.path.dirname(yul_file)
    yul_base = os.path.basename(yul_file).replace("_standard_input.json", "")

    print(f"Procesando archivo: {yul_file}")

    # Run external commands
    solc_command = [
        "./solc-objects",
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
        "-solc", "./solc-objects",
        "-o", f"/tmp/{yul_base}",
    ]
    log_file = os.path.join(yul_dir, f"{yul_base}.log")
    with open(log_file, "w") as log:
        subprocess.run(grey_command, stdout=log)

    print(" ".join(grey_command))

    # Copy results
    tmp_dir = f"/tmp/{yul_base}"
    if os.path.isdir(tmp_dir):
        for asm_file in Path(tmp_dir).rglob("*_asm.json"):
            shutil.copy(str(asm_file), yul_dir)

    test_file = os.path.join(yul_dir, "test")
    if os.path.isfile(test_file):
        replace_command = [
            "python3",
            "scripts/replace_bytecode_test.py",
            test_file,
            log_file,
        ]
        subprocess.run(replace_command)
        print(" ".join(replace_command))

        testrunner_command_original = [
            "../solidity/build/test/tools/testrunner",
            "../evmone/lib/libevmone.so.0.13.0",
            test_file,
            os.path.join(yul_dir, "resultOriginal.json"),
        ]
        subprocess.run(testrunner_command_original)

        testrunner_command_grey = [
            "../solidity/build/test/tools/testrunner",
            "../evmone/lib/libevmone.so.0.13.0",
            f"{yul_dir}/test",
            os.path.join(yul_dir, "resultGrey.json"),
        ]
        subprocess.run(testrunner_command_grey)

        # Compare results
        result_original = os.path.join(yul_dir, "resultOriginal.json")
        result_grey = os.path.join(yul_dir, "resultGrey.json")
        if filecmp.cmp(result_original, result_grey, shallow=False):
            print("[RES]: Test passed.")
            count_command = [
                "python3",
                "scripts/count-num-ins.py",
                output_file,
                log_file,
            ]
            subprocess.run(count_command)
            print(" ".join(count_command))
        else:
            print("[RES]: Test failed.")
    else:
        print("Test not found")


def run_experiments(n_cpus):
    # Change the directory to the root

    os.chdir("..")
    DIRECTORIO_TESTS = "tests_evmone"

    # Check if the directory exists
    if not os.path.isdir(DIRECTORIO_TESTS):
        print(f"El directorio {DIRECTORIO_TESTS} no existe.")
        exit(1)

    # Find all files matching "*standard_input.json" in the directory
    yul_files = list(Path(DIRECTORIO_TESTS).rglob("*standard_input.json"))
    with mp.Pool(n_cpus) as p:
        p.map(execute_yul_test, yul_files)
    print("Procesamiento completado.")


if __name__ == "__main__":
    if len(sys.argv) == 2:
        n_cpus = int(sys.argv[1])
    else:
        n_cpus = max(mp.cpu_count() - 1, 1)
    run_experiments(n_cpus)
