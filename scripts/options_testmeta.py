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

    for json_file in glob.glob(str(path_to_tests.joinpath("*/*_standard_input.json"))):
        parent_dir = Path(Path(json_file).parent).name
        with open(json_file, 'r') as f:
            json_info = json.load(f)
        try:
            json_info["settings"] = name2meta[parent_dir]["settings"]
        except:
            print(parent_dir)
            continue


if __name__ == "__main__":
    name2dict = options_from_testtrace_meta()
    set_compilation_options(Path(sys.argv[1]), name2dict)
