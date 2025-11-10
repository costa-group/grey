"""
For all the files in a folder, computes the size of each contract
"""
import sys
import os
import json
import subprocess
import shlex
import resource
import tempfile
from pathlib import Path

import pandas as pd


def run_command(cmd):
    solc_p = subprocess.Popen(shlex.split(cmd), stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE)
    outs, err = solc_p.communicate()
    return outs.decode(), err.decode()


def run_and_measure_command(cmd):
    usage_start = resource.getrusage(resource.RUSAGE_CHILDREN)
    solution, err = run_command(cmd)
    usage_stop = resource.getrusage(resource.RUSAGE_CHILDREN)
    return solution, err, usage_stop.ru_utime + usage_stop.ru_stime - usage_start.ru_utime - usage_start.ru_stime


def compile_json_input(source_code_dict):
    optimization_settings = {"enabled": True}

    # Output selection is legacyAssembly
    output_selection = {'*': {'*': ['evm.bytecode.object']}}

    source_code_dict["settings"]["optimizer"] = optimization_settings
    source_code_dict["settings"]["outputSelection"] = output_selection

    # Remove the hash from the code
    source_code_dict["settings"]["metadata"] = {
            "appendCBOR": False
        }

    source_code_dict["settings"]["viaIR"] = True

    fd, tmp_file = tempfile.mkstemp(".json")

    with open(tmp_file, 'w') as f:
        f.write(json.dumps(source_code_dict))

    command = f"solc --standard-json {tmp_file}"
    output, error, total_time = run_and_measure_command(command)
    # print(command)

    output_dict = json.loads(output)

    # Check no field errors appear when parsing as a json and one of the messages is indeed an error
    # (see https://docs.soliditylang.org/en/v0.8.17/using-the-compiler.html)
    if "errors" in output_dict and any(error_msg["severity"] == "error" for error_msg in output_dict["errors"]):
        print(f"Error {output_dict}")
    else:
        if error != "":
            print(f"Warning error")
            print(error)
            print("")

    os.close(fd)
    os.remove(tmp_file)

    return output_dict, total_time


def extract_info(output_dict):
    contract_info = []
    added = dict()

    for file_name in output_dict["contracts"]:
        for contract_name, contract in output_dict["contracts"][file_name].items():
            if isinstance(contract, dict):
                evm = contract["evm"]["bytecode"]["object"]
                if len(evm) > 0:
                    size = len(evm) // 2

                    if contract_name in added:
                        assert added[contract_name] == size, f"Expect same name in {contract_name} for file {file_name}"
                    else:
                        added[contract_name] = size
                        contract_info.append({"contract": f"{contract_name}",
                                              "bin_code": evm, "num_bytes": size})

    return contract_info


def compile_files(initial_folder: Path, final_folder: Path):
    final_folder.mkdir(exist_ok=True, parents=True)
    # print(list(initial_folder.glob("*.json")))
    for json_file in initial_folder.glob("*.json"):
        path_file = Path(Path(json_file).name).stem
        with open(json_file, 'r') as f:
            contract_dict = json.load(f)
        try:
            output, total_time = compile_json_input(contract_dict)
            contract_info = extract_info(output)
            pd.DataFrame(contract_info).to_csv(final_folder.joinpath(str(path_file) + ".csv"))
        except Exception as e:
            print(f"Error in {path_file}: {e}")

if __name__ == "__main__":
    etherscan_output_folder, target_folder = Path(sys.argv[1]), Path(sys.argv[2])
    compile_files(etherscan_output_folder, target_folder)
