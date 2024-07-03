"""
Compiles a smart contract (in either of the formats used in Etherscan)
into the yul representation
"""

import glob
import json
import shutil
import sys
import os
import re
import subprocess
import shlex
import logging
from pathlib import Path
import pandas as pd
from typing import Dict, Any
import tempfile
import traceback


VIA_IR_ENABLED = True


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
    fd, tmp_file = tempfile.mkstemp()

    with open(tmp_file, 'w') as f:
        f.write(source_code_plain)

    optimization_flags = "--via-ir" if VIA_IR_ENABLED else ""
    command = f"solc --combined-json asm --optimize {optimization_flags} --pretty-json {tmp_file}"
    output, error = run_command(command)
    # print(command)

    if "Error:" in error:
        logging.error(f"File: {contract_address}")
        logging.error(f"Errors: {error}")
    else:
        if error != "":
            logging.warning(f"Warning in Contract {contract_address}")
            logging.warning(error)
        with open(file_path, 'w') as f:
            f.write(output)

    os.close(fd)
    os.remove(tmp_file)


def compile_json_input(source_code_dict: Dict[str, Any], contract_address: str, version: str, file_path: Path):
    optimization_settings = {"enabled": True}

    # Output selection is legacyAssembly
    output_selection = {'*': {'*': ['evm.legacyAssembly']}}

    source_code_dict["settings"]["optimizer"] = optimization_settings
    source_code_dict["settings"]["outputSelection"] = output_selection
    if VIA_IR_ENABLED:
        source_code_dict["settings"]["viaIR"] = True

    fd, tmp_file = tempfile.mkstemp()

    with open(tmp_file, 'w') as f:
        f.write(json.dumps(source_code_dict))

    command = f"solc --standard-json {tmp_file}"
    output, error = run_command(command)
    # print(command)

    output_dict = json.loads(output)

    # with open(Path(file_path).parent.joinpath("extended.json"), 'w') as f:
    #     json.dump(output_dict, f, indent=4)

    # Check no field errors appear when parsing as a json and one of the messages is indeed an error
    # (see https://docs.soliditylang.org/en/v0.8.17/using-the-compiler.html)
    if "errors" in output_dict and any(error_msg["severity"] == "error" for error_msg in output_dict["errors"]):
        logging.error(f"File: {contract_address}")
        logging.error(f"Errors: {output_dict['errors']}")
    else:
        if error != "":
            logging.warning(f"Warning in Contract {contract_address}")
            logging.warning(error)

        final_json_asm = {}

        final_json_asm_contracts = {}
        # Modify the format to match --combined-json asm format
        for contract in output_dict["contracts"]:
            current_contract = output_dict["contracts"][contract]
            for subcontract, subcontract_info in current_contract.items():
                subcontract_name = f"{contract}:{subcontract}"
                info = subcontract_info["evm"]["legacyAssembly"]

                # Info can be either none or a dict following the same structure as the usual asm format
                asm_info = {} if info is None else {"asm": info}

                final_json_asm_contracts[subcontract_name] = asm_info
            # contract_name = current_contract.values()[0]

        final_json_asm["version"] = version
        final_json_asm["contracts"] = final_json_asm_contracts

        # Store directly the output from solc
        # with open(file_path, 'w') as f:
        #     f.write(output)

        # Store the output following the asm format
        with open(file_path, 'w') as f:
            json.dump(final_json_asm, f, indent=4)

    os.close(fd)
    os.remove(tmp_file)


def compile_multiple_sources(source_code_dict: Dict[str, Dict[str, str]], contract_address: str, optimization_used: bool,
                             runs: int, deployed_contract: str, file_path: Path):
    tmp_dir = tempfile.mkdtemp()
    tmp_folder = Path(tmp_dir)

    # Key: contract .sol file
    # Value: source code
    contract_to_compile = None
    for sol_file_name, sol_file_dict in source_code_dict.items():

        sol_file_contents = sol_file_dict["content"]
        sol_file = tmp_folder.joinpath(sol_file_name)
        with open(sol_file, 'w') as f:
            f.write(sol_file_contents)

        # Check main contract
        if f"contract {deployed_contract} " in sol_file_contents:
            if contract_to_compile is not None:
                logging.error(f"Contract {deployed_contract} appears in two files")
            contract_to_compile = sol_file

    if contract_to_compile is None:
        logging.error(f"Contract {deployed_contract} has not been found in any of the sol files")

    old_path = os.getcwd()

    os.chdir(tmp_folder)

    optimization_flags = "--via-ir" if VIA_IR_ENABLED else ""
    command = f"solc --combined-json asm --optimize {optimization_flags} --pretty-json {contract_to_compile}"
    output, error = run_command(command)
    os.chdir(old_path)

    # print(command)

    if "Error:" in error:
        logging.error(f"File: {contract_address}")
        logging.error(f"Errors: {error}")
    else:
        if error != "":
            logging.warning(f"Warning in Contract {contract_address}")
            logging.warning(error)

        with open(file_path, 'w') as f:
            f.write(output)

    shutil.rmtree(tmp_dir)


def compile_from_etherscan_json(etherscan_info: Dict, resulting_file: Path, address: str):
    # Skip if version <= 0.8.*
    compiler_version = etherscan_info[0]["CompilerVersion"]
    if "v0.8" not in compiler_version:
        logging.log(f"Skipped {address}. Compiler version: {compiler_version}")
        return

    version_output, _ = run_command("solc --version")
    version_to_optimize = extract_version_from_output(version_output)

    source_code = change_pragma(etherscan_info[0]["SourceCode"], version_to_optimize)
    executable = get_executable(compiler_version)
    main_contract = etherscan_info[0]["ContractName"]
    is_optimized = True if int(etherscan_info[0]["OptimizationUsed"]) == 1 else False
    n_runs = int(etherscan_info[0]["Runs"])

    try:
        code_dict = json.loads(source_code[1:-1])
        logging.log(f"Json input {address}")
        compile_json_input(code_dict, address, version_to_optimize, resulting_file)
    except Exception as e:
        try:
            code_dict = json.loads(source_code)
            logging.log(f"Multi sol input {address}")
            compile_multiple_sources(code_dict, address, is_optimized, n_runs, main_contract, resulting_file)

        except Exception as e:
            logging.log(f"Single sol input {address}")
            compile_source_code(source_code, address, is_optimized, n_runs, resulting_file)


def compile_files_from_folders():
    initial_folder, final_folder = Path(sys.argv[1]), Path(sys.argv[2])

    # Create repo (even if exists)
    final_folder.mkdir(parents=True, exist_ok=True)

    error_files = []

    for i, etherscan_json_file in enumerate(glob.glob(str(initial_folder.joinpath("*.json")))):
        address = Path(Path(etherscan_json_file).name).stem

        # Load file
        with open(etherscan_json_file, 'r') as f:
            etherscan_info = json.load(f)

        filename = final_folder.joinpath(f"{address}.yul")
        compile_from_etherscan_json(etherscan_info, filename, address)


if __name__ == "__main__":
    compile_files_from_folders()
