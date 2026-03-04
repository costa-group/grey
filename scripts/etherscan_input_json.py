"""
Given the output from etherscan downloader,
tries to generate the JSON input file and compile it
"""

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


def single_file2json_input(source_code_plain: str, contract_address: str, file_path: Path):
    standard_json_input = {
        "language": "Solidity",
        "sources": {
            f"{contract_address}.sol": {
                "content": source_code_plain
            }
        },
        "settings": {}
    }
    compile_json_input(standard_json_input, contract_address, file_path)


def multiple_files2json_input(source_code_dict: Dict[str, Dict[str, str]],
                              contract_address: str, file_path: Path):
    # It is directly on the requested format
    standard_json_input = {
        "language": "Solidity",
        "sources": source_code_dict,
        "settings": {}
    }
    compile_json_input(standard_json_input, contract_address, file_path)


def compile_json_input(source_code_dict: Dict[str, Any], contract_address: str, file_path: Path):
    optimization_settings = {"enabled": True}

    # Output selection is yulCFGJson
    output_selection = {'*': {'*': ['yulCFGJson']}}

    source_code_dict["settings"]["optimizer"] = optimization_settings
    source_code_dict["settings"]["outputSelection"] = output_selection
    source_code_dict["settings"]["viaIR"] = True

    source_file = file_path.joinpath(f"{address}.json")
    with open(source_file, 'w') as f:
        f.write(json.dumps(source_code_dict, indent=4))

    command = f"solc --standard-json {source_file}"
    output, error = run_command(command)
    # print(command)

    output_dict = json.loads(output)

    with open(Path(file_path).parent.joinpath("extended.json"), 'w') as f:
        json.dump(output_dict, f, indent=4)

    # Check no field errors appear when parsing as a json and one of the messages is indeed an error
    # (see https://docs.soliditylang.org/en/v0.8.17/using-the-compiler.html)
    if "errors" in output_dict and any(error_msg["severity"] == "error" for error_msg in output_dict["errors"]):
        error_dict = {f"{key}_{j}": error_msg[key] for j, error_msg in enumerate(output_dict["errors"]) for key in error_msg}
        error_files.append({"file": contract_address, **error_dict})

        # Erase the folder in which the contract is stored
        shutil.rmtree(file_path)

    else:
        if error != "":
            print(f"Warning in Contract {contract_address}")
            print(error)
            print("")

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
        compiler_version = etherscan_info["CompilerVersion"]
        if "v0.8" not in compiler_version:
            print(f"Skipped {address}. Compiler version: {compiler_version}")
            continue

        version_output, _ = run_command("solc --version")
        version_to_optimize = extract_version_from_output(version_output)

        source_code = change_pragma(etherscan_info["SourceCode"], version_to_optimize)
        executable = get_executable(compiler_version)
        main_contract = etherscan_info["ContractName"]
        is_optimized = True if int(etherscan_info["OptimizationUsed"]) == 1 else False
        n_runs = int(etherscan_info["Runs"])

        address_path = final_folder_path.joinpath(address)
        address_path.mkdir(exist_ok=True, parents=True)
        try:
            code_dict = json.loads(source_code[1:-1])
            print(f"{i} Json input {address}")
            compile_json_input(code_dict, address, address_path)
        except Exception as e:
            try:
                code_dict = json.loads(source_code)
                print(f"{i} Multi sol input {address}")
                multiple_files2json_input(code_dict, address, address_path)

            except Exception as e:
                print(f"{i} Single sol input {address}")
                single_file2json_input(source_code, address, address_path)
    pd.DataFrame(error_files).to_csv(final_folder_path.joinpath(f'log.csv').resolve())
