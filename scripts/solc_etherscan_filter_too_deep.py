import glob
import json
import shutil
import sys
import os
import re
import subprocess
import shlex
from pathlib import Path
import pandas as pd
from typing import Dict, Any
import tempfile
import traceback


VIA_IR_ENABLED = False


def run_command(cmd):
    solc_p = subprocess.Popen(shlex.split(cmd), stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE)
    outs, err = solc_p.communicate()
    return outs.decode(), err.decode()


def get_executable(version_with_commit: str) -> str:
    pattern = re.compile("v([0-9]+\.[0-9]+\.[0-9]+)+")
    match = pattern.search(version_with_commit)
    if match is not None:
        return match.group(1)
    else:
        raise ValueError(f"{version_with_commit} does not contain solc version in proper format")


def extract_version_from_output(output_sol: str) -> str:
    pattern = re.compile("Version: ([0-9]+\.[0-9]+\.[0-9]+)\+")
    match = pattern.search(output_sol)
    if match is not None:
        return match.group(1)
    else:
        raise ValueError(f"{output_sol} does not contain solc version in proper format")


def change_pragma(initial_contract: str, pragma_name: str = "0.8.17"):
    pattern = re.compile("pragma solidity .*?;")
    contract_with_pragma = re.sub(pattern, f"pragma solidity ^{pragma_name};",initial_contract)
    return contract_with_pragma


def compile_source_code(source_code_plain: str, contract_address: str, optimization_used: bool,
                        runs: int, file_path: Path):
    source_file = file_path.joinpath(f"{address}.sol")
    with open(source_file, 'w') as f:
        f.write(source_code_plain)

    optimization_flags = "--via-ir" if VIA_IR_ENABLED else ""
    command = f"solc --optimize {optimization_flags} --bin {source_file}"
    output, error = run_command(command)
    # print(command)

    if "Error:" in error:
        print(f"Error in {contract_address}")
        error_files.append({"file": contract_address, "reason": error, "output": output})
    else:
        if error != "":
            print(f"Warning in Contract {contract_address}")
            print(error)
            print("")

        # Erase the contract
        os.unlink(source_file)


def compile_json_input(source_code_dict: Dict[str, Any], contract_address: str, version: str, file_path: Path):
    optimization_settings = {"enabled": True}

    # Output selection is legacyAssembly
    output_selection = {'*': {'*': ['evm.legacyAssembly']}}

    source_code_dict["settings"]["optimizer"] = optimization_settings
    source_code_dict["settings"]["outputSelection"] = output_selection
    if VIA_IR_ENABLED:
        source_code_dict["settings"]["viaIR"] = True
    else:
        source_code_dict["settings"]["viaIR"] = False

    source_file = file_path.joinpath(f"{address}.json")
    with open(source_file, 'w') as f:
        f.write(json.dumps(source_code_dict))

    command = f"solc --standard-json {source_file}"
    output, error = run_command(command)
    # print(command)

    output_dict = json.loads(output)

    # with open(Path(file_path).parent.joinpath("extended.json"), 'w') as f:
    #     json.dump(output_dict, f, indent=4)

    # Check no field errors appear when parsing as a json and one of the messages is indeed an error
    # (see https://docs.soliditylang.org/en/v0.8.17/using-the-compiler.html)
    if "errors" in output_dict and any(error_msg["severity"] == "error" for error_msg in output_dict["errors"]):
        print("STACK TOO DEEP")
        error_dict = {f"{key}_{j}": error_msg[key] for j, error_msg in enumerate(output_dict["errors"]) for key in error_msg}
        error_files.append({"file": contract_address, **error_dict})
    else:
        if error != "":
            print(f"Warning in Contract {contract_address}")
            print(error)
            print("")

        # Erase the contract
        os.unlink(source_file)

def compile_multiple_sources(source_code_dict: Dict[str, Dict[str, str]], contract_address: str, optimization_used: bool,
                             runs: int, deployed_contract: str, file_path: Path):

    # Key: contract .sol file
    # Value: source code
    contract_to_compile = None
    for sol_file_name, sol_file_dict in source_code_dict.items():

        sol_file_contents = sol_file_dict["content"]
        sol_file = file_path.joinpath(sol_file_name)
        with open(sol_file, 'w') as f:
            f.write(sol_file_contents)

        # Check main contract
        if f"contract {deployed_contract} " in sol_file_contents:
            if contract_to_compile is not None:
                print(contract_to_compile, sol_file_name)
                raise ValueError(f"Contract {deployed_contract} appears in two files")
            contract_to_compile = sol_file

    if contract_to_compile is None:
        raise ValueError(f"Contract {deployed_contract} has not been found in any of the sol files")

    old_path = os.getcwd()

    os.chdir(file_path)

    optimization_flags = "--via-ir" if VIA_IR_ENABLED else ""
    command = f"solc --bin --optimize {optimization_flags} {contract_to_compile}"
    output, error = run_command(command)
    os.chdir(old_path)

    # print(command)

    if "Error:" in error:
        print(f"Error in {deployed_contract}")
        error_files.append({"file": deployed_contract, "reason": error, "output": output})
    else:
        if error != "":
            print(f"Warning in Contract {contract_address}")
            print(error)
            print("")

        # Erase the contract
        shutil.rmtree(file_path)


if __name__ == "__main__":
    etherscan_output_folder, final_folder = sys.argv[1], sys.argv[2]

    final_folder_path = Path(final_folder)

    # Create repo (even if exists)
    final_folder_path.mkdir(parents=True, exist_ok=True)

    error_files = []
    current = 0

    for i, etherscan_json_file in enumerate(glob.glob(f"{etherscan_output_folder}/*.json")):
        address = etherscan_json_file.split("/")[-1][:-5]
        print(etherscan_json_file)

        # Load file
        with open(etherscan_json_file, 'r') as f:
            etherscan_info = json.load(f)

        # Skip if version <= 0.8.*
        compiler_version = etherscan_info[0]["CompilerVersion"]
        if "v0.8" not in compiler_version:
            print(f"Skipped {address}. Compiler version: {compiler_version}")
            continue

        version_output, _ = run_command("solc --version")
        version_to_optimize = extract_version_from_output(version_output)
        print(version_output)

        source_code = change_pragma(etherscan_info[0]["SourceCode"], version_to_optimize)
        executable = get_executable(compiler_version)
        main_contract = etherscan_info[0]["ContractName"]
        is_optimized = True if int(etherscan_info[0]["OptimizationUsed"]) == 1 else False
        n_runs = int(etherscan_info[0]["Runs"])

        address_path = final_folder_path # final_folder_path.joinpath(address)
        address_path.mkdir(exist_ok=True, parents=True)
        try:
            code_dict = json.loads(source_code[1:-1])
            print(f"{i} Json input {address}")
            compile_json_input(code_dict, address, version_to_optimize, address_path)
        except Exception as e:
            try:
                code_dict = json.loads(source_code)
                print(f"{i} Multi sol input {address}")
                compile_multiple_sources(code_dict, address, is_optimized, n_runs, main_contract, address_path)

            except Exception as e:
                print(f"{i} Single sol input {address}")
                compile_source_code(source_code, address, is_optimized, n_runs, address_path)
    pd.DataFrame(error_files).to_csv(final_folder_path.joinpath(f'log.csv').resolve())
