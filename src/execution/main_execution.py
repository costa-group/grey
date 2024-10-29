import argparse
import json
from typing import Dict, Any, Optional
from pathlib import Path
from timeit import default_timer as dtimer
import pandas as pd

from parser.utils_parser import split_json
from global_params.types import Yul_CFG_T
from parser.optimizable_block_list import compute_sub_block_cfg
from parser.parser import parse_CFG_from_json_dict
from parser.cfg import store_sfs_json, CFG
from execution.sol_compilation import SolidityCompilation
from greedy.greedy import greedy_standalone
from solution_generation.statistics import generate_statistics_info
from solution_generation.reconstruct_bytecode import asm_from_ids, asm_from_cfg, store_asm_output
from liveness.liveness_analysis import dot_from_analysis
from liveness.layout_generation import layout_generation
from cfg_methods.preprocessing_methods import preprocess_cfg


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GREEN Project")

    input_options = parser.add_argument_group("Input Options")

    input_options.add_argument("-s",  "--source", type=str, help="Local source file name. By default, it assumes the"
                                                                 "Yul CFG JSON format", required=True)
    input_options.add_argument("-if", "--input-format", dest="input_format", type=str,
                               help="Sets the input format: a sol file, the standard-json input or a Yul CFG JSON."
                                    "By default, it assumes the Yul CFG.", choices=["sol", "standard-json", "yul-cfg"],
                               default="yul-cfg")
    input_options.add_argument("-c", "--contract", type=str, dest="contract",
                               help="Specify which contract must be synthesized. "
                                    "If no contract is specified, all contracts synthesized.")
    input_options.add_argument("-solc", "--solc", type=str, dest="solc_executable", default="solc",
                               help="Solc executable. By default, it assumes it can invoke 'solc'")

    output_options = parser.add_argument_group("Output Options")
    output_options.add_argument("-o", "--folder", type=str, help="Dir to store the results.", default="/tmp/grey/")
    output_options.add_argument("-v", "--visualize", action="store_true", dest="visualize",
                                help="Generates a dot file for each object in the JSON, "
                                     "showcasing the results from the liveness analysis")

    synthesis_options = parser.add_argument_group("Synthesis Options")
    synthesis_options.add_argument("-g", "--greedy", action="store_true", help="Enables the greedy algorithm")
    synthesis_options.add_argument("-bt", "--builtin-ops", action="store_true", dest="builtin",
                                   help="Keeps the original builtin opcodes")

    args = parser.parse_args()
    return args


def yul_cfg_dict_from_format(input_format: str, filename: str, contract: Optional[str],
                             solc_executable: str = "solc") -> Dict[str, Yul_CFG_T]:
    """
    Returns a dict of the Yul CFG JSONS that are generated from the compilation of a contract
    """
    if input_format == "yul-cfg":
        # We assume there can be multiple JSONS inside a single file
        return split_json(filename)
    elif input_format == "sol":
        return SolidityCompilation.from_single_solidity_code(filename, contract, solc_executable=solc_executable)
    elif input_format == "standard-json":
        # First load the input file
        with open(filename, 'r') as f:
            input_contract = json.load(f)
        return SolidityCompilation.from_json_input(input_contract, contract, solc_executable=solc_executable)
    else:
        raise ValueError(f"Input format {input_format} not recognized.")


def analyze_single_cfg(cfg: CFG, tags_dict, final_dir: Path, dot_file_dir: Path, args: argparse.Namespace):
    preprocess_cfg(cfg, dot_file_dir)

    if args.visualize:
        liveness_info = dot_from_analysis(cfg, dot_file_dir)

    x = dtimer()
    jsons = layout_generation(cfg, dot_file_dir)

    sfs_final_dir = final_dir.joinpath("sfs")
    sfs_final_dir.mkdir(exist_ok=True, parents=True)
    y = dtimer()

    print("Layout generation: " + str(y - x) + "s")

    block_name2asm = dict()

    json_asm_contract = {}
    
    if args.greedy:
        csv_rows = []
        for block_name, sfs in jsons.items():
            store_sfs_json(block_name, sfs, sfs_final_dir)
            _, time, solution_found = greedy_standalone(sfs)
            csv_row = generate_statistics_info(block_name, solution_found, time, sfs)
            solution_asm = asm_from_ids(sfs, solution_found)
            block_name2asm[block_name] = solution_asm
            csv_rows.append(csv_row)

        # Generate complete asm from CFG object + dict

        json_asm_contract = asm_from_cfg(cfg, block_name2asm, tags_dict, args.source)
        df = pd.DataFrame(csv_rows)
        df.to_csv(final_dir.joinpath("statistics.csv"))

    return json_asm_contract
        

def main():
    print("Green Main")
    args = parse_args()

    x = dtimer()
    json_dict = yul_cfg_dict_from_format(args.input_format, args.source,
                                         args.contract, args.solc_executable)
    with open('intermediate.json', 'w') as f:
        json.dump(json_dict, f)
    cfgs, tags = parse_CFG_from_json_dict(json_dict, args.builtin)
    
    y = dtimer()

    print("CFG Parser: "+str(y-x)+"s")

    final_dir = Path(args.folder)

    final_dir.mkdir(exist_ok=True, parents=True)

    dot_file_dir = final_dir.joinpath("liveness")
    dot_file_dir.mkdir(exist_ok=True, parents=True)

    asm_output = {}

    asm_out_dir = final_dir.joinpath("asm_out_files")
    asm_out_dir.mkdir(exist_ok=True, parents=True)
    
    for i in cfgs:
        cfg = cfgs[i]
        tags_dict = tags[i]
        json_asm_contract = analyze_single_cfg(cfg,tags_dict,final_dir,dot_file_dir,args)
        
        asm_output = asm_output | json_asm_contract

    asm_contracts = {"contracts": asm_output}

    source_name = args.source.split(".")[0]
    store_asm_output(asm_out_dir, asm_contracts, source_name.split("/")[-1])
    
    # asm_contracts["version"] = #TODO Call to solc version
