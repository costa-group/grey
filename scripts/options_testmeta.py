import glob
import os
import json
import sys
from pathlib import Path
from typing import Dict


def folder_name_from_path(path_to_sol: str) -> str:
    """
    Generates the name from the path to the solidity file according to our representation in the
    semantic tests.
    """
    return '_'.join(str(Path(path_to_sol).with_suffix('')).split("/")[1:])


def options_from_testtrace_meta() -> Dict:
    with open("testtrace_meta", 'r') as f:
        testtrace_dict = json.load(f)

    new_dict = {folder_name_from_path(key): value for key, value in testtrace_dict.items()}
    return new_dict


def set_compilation_options(path_to_tests: Path, name2meta: Dict) -> None:
    # Load the options from the tesstrace meta
    found, not_found = 0, 0
    files_to_analyze = glob.glob(str(path_to_tests.joinpath("*/*_standard_input.json")))
    for json_file in files_to_analyze:
        parent_dir = Path(Path(json_file).parent).name
        with open(json_file, 'r') as f:
            json_info = json.load(f)
            file_options = name2meta.get(parent_dir, None)

            if file_options is not None:            
                file_options["settings"].pop("compilationTarget", None)
                file_options["settings"]["metadata"].pop("bytecodeHash", None)

                if "outputSelection" in json_info["settings"]:
                    file_options["settings"]["outputSelection"] = json_info["settings"]["outputSelection"]

                json_info["settings"] = file_options["settings"]
                
                found += 1
            else:
                # If the test does not appear in the testtrace file, we just replace
                # by standard compilation options
                json_info["settings"]["viaIR"] = True
                json_info["settings"]["metadata"] = {}
                json_info["settings"]["metadata"]["appendCBOR"] = False
                json_info["settings"]["optimizer"] = {}
                json_info["settings"]["optimizer"]["enabled"] = True
                json_info["settings"]["optimizer"]["runs"] = 200
                not_found += 1

        # Ensure there is a default output selection for the settings before replacing the options
        if "outputSelection" not in json_info["settings"]:
            json_info["settings"]["outputSelection"] = {"*": {"*": ["abi", "metadata", "evm.bytecode", "evm.deployedBytecode", "evm.methodIdentifiers"]}}

        with open(json_file, 'w') as f:
            json.dump(json_info, f)
            print(json_file, "modified")
                
    print("Found:", found, "Not found:", not_found)

if __name__ == "__main__":
    name2dict = options_from_testtrace_meta()
    set_compilation_options(Path(sys.argv[1]), name2dict)
