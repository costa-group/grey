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
from typing import Dict, Any
import tempfile

# Optimization with via-ir enabled
VIA_IR_ENABLED = True

# Solc version
solc_version = "./solc-new"


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

    command = f"{solc_version} --yul-cfg-json --optimize --pretty-json {tmp_file}"
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
    output_selection = {'*': {'*': ['yulCFGJson']}}

    source_code_dict["settings"]["optimizer"] = optimization_settings
    source_code_dict["settings"]["outputSelection"] = output_selection
    if VIA_IR_ENABLED:
        source_code_dict["settings"]["viaIR"] = True

    fd, tmp_file = tempfile.mkstemp()

    with open(tmp_file, 'w') as f:
        f.write(json.dumps(source_code_dict))

    command = f"{solc_version} --standard-json {tmp_file}"
    output, error = run_command(command)
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

        # Produce a json file for each contract
        for filename in output_dict["contracts"]:
            current_file = output_dict["contracts"][filename]
            for contract_name in current_file:
                yul_cfg_current = current_file[contract_name]["yulCFGJson"]


                if yul_cfg_current is not None:
                    # Modify file path to include the concrete contract name
                    file_with_no_extension = Path(file_path.name).stem
                    parent = file_path.parent
                    resulting_file = parent.joinpath(file_with_no_extension + f"_{contract_name}.json")

                    # Store the output following the asm format
                    with open(resulting_file, 'w') as f:
                        json.dump(yul_cfg_current, f, indent=4)

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
    shutil.copy("solc-new", tmp_folder)
    os.chdir(tmp_folder)

    command = f"{solc_version} --yul-cfg-json --optimize --pretty-json {contract_to_compile}"
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
        logging.log(1, f"Skipped {address}. Compiler version: {compiler_version}")
        return

    version_output, _ = run_command("solc --version")
    version_to_optimize = extract_version_from_output(version_output)

    source_code = change_pragma(etherscan_info[0]["SourceCode"], version_to_optimize)
    main_contract = etherscan_info[0]["ContractName"]
    is_optimized = True if int(etherscan_info[0]["OptimizationUsed"]) == 1 else False
    n_runs = int(etherscan_info[0]["Runs"])

    try:
        code_dict = json.loads(source_code[1:-1])
        logging.log(1, f"Json input {address}")
        compile_json_input(code_dict, address, version_to_optimize, resulting_file)
    except Exception as e:
        try:
            code_dict = json.loads(source_code)
            logging.log(1, f"Multi sol input {address}")
            compile_multiple_sources(code_dict, address, is_optimized, n_runs, main_contract, resulting_file)

        except Exception as e:
            logging.log(1, f"Single sol input {address}")
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
    logging.basicConfig(level=1)
    compile_files_from_folders()
