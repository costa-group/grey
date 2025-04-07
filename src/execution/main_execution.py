import argparse
import json
from typing import Dict, Optional
from pathlib import Path
from timeit import default_timer as dtimer

from parser.utils_parser import split_json
from global_params.types import Yul_CFG_T
from parser.parser import parse_CFG_from_json_dict
from parser.cfg import CFG
from execution.sol_compilation import SolidityCompilation
from solution_generation.reconstruct_bytecode import asm_from_cfg, store_asm_output,  store_binary_output, store_asm_standard_json_output
from greedy.ids_from_spec import cfg_spec_ids
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
        return split_json(filename), {}
    elif input_format == "sol":
        return SolidityCompilation.from_single_solidity_code(filename, contract, solc_executable=solc_executable), {}
    elif input_format == "standard-json":
        # First load the input file
        with open(filename, 'r') as f:
            input_contract = json.load(f)
            settings_opt = input_contract["settings"]
        return SolidityCompilation.from_json_input(input_contract, contract, solc_executable=solc_executable), settings_opt
    else:
        raise ValueError(f"Input format {input_format} not recognized.")


def analyze_single_cfg(cfg: CFG, final_dir: Path, args: argparse.Namespace):
    dot_file_dir = final_dir.joinpath("liveness")
    dot_file_dir.mkdir(exist_ok=True, parents=True)
    tags_dict = preprocess_cfg(cfg, dot_file_dir, args.visualize)

    x = dtimer()
    layout_generation(cfg, final_dir.joinpath("stack_layouts"))
    y = dtimer()

    print("Layout generation: " + str(y - x) + "s")

    cfg_spec_ids(cfg, final_dir.joinpath("statistics.csv"), args.visualize)

    if args.visualize:
        asm_code = final_dir.joinpath("asm")
        asm_code.mkdir(exist_ok=True, parents=True)
    else:
        asm_code = None
    json_asm_contract = asm_from_cfg(cfg, tags_dict, args.source, asm_code)
    return json_asm_contract


def main(args):
    print("Grey Main")

    x = dtimer()
    json_dict, settings = yul_cfg_dict_from_format(args.input_format, args.source,
                                         args.contract, args.solc_executable)
    if args.visualize:
        with open('intermediate.json', 'w') as f:
            json.dump(json_dict, f, indent=4)

    cfgs = parse_CFG_from_json_dict(json_dict, args.builtin)
    
    y = dtimer()

    print("CFG Parser: "+str(y-x)+"s")

    final_dir = Path(args.folder)

    final_dir.mkdir(exist_ok=True, parents=True)
    asm_output = {}

    for cfg_name, cfg in cfgs.items():
  #      print("Synthesizing...", cfg_name)
        cfg_dir = final_dir.joinpath(cfg_name)
        
        asm_contract = analyze_single_cfg(cfg, cfg_dir, args)

        if args.visualize:
            assembly_path = store_asm_output(asm_contract, cfg_name, cfg_dir)

        std_assembly_path = store_asm_standard_json_output(asm_contract, cfg_name, cfg_dir, settings)
        #print(std_assembly_path)
        #synt_binary = SolidityCompilation.importer_assembly_file(assembly_path, solc_executable=args.solc_executable)
        synt_binary_stdjson = SolidityCompilation.importer_assembly_standard_json_file(std_assembly_path, deployed_contract = cfg_name, solc_executable = args.solc_executable)

        if args.visualize:
            print("Contract: " + cfg_name + " -> EVM Code: " + synt_binary_stdjson)
            store_binary_output(cfg_name, synt_binary_stdjson, cfg_dir)
