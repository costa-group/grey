import argparse
import json
import re
from typing import Dict, Optional, List
from pathlib import Path
from timeit import default_timer as dtimer
from collections import defaultdict

import pandas as pd

from parser.utils_parser import split_json
from global_params.types import Yul_CFG_T
from parser.parser import parse_CFG_from_json_dict
from parser.cfg import CFG
from execution.sol_compilation import SolidityCompilation, importer_deduplicates_blocks
from solution_generation.reconstruct_bytecode import asm_from_cfg, store_asm_output, store_binary_output, \
    store_asm_standard_json_output
from greedy.ids_from_spec import cfg_spec_ids
from liveness.layout_generation import layout_generation
from cfg_methods.preprocessing_methods import preprocess_cfg
from solution_generation.bytecode2asm import asm_from_opcodes
from reparation.repair_unreachable import repair_cfg
from analysis.solution_analysis import function_frequency
import global_params.constants as constants
from global_params.debug import debug_file
from solution_generation.store_sfs import sfs_from_cfg

global times
times = []


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
        return SolidityCompilation.from_json_input(input_contract, contract, original_folder=str(Path(filename).parent),
                                                   solc_executable=solc_executable), settings_opt
    else:
        raise ValueError(f"Input format {input_format} not recognized.")


def analyze_single_cfg(cfg: CFG, final_dir: Path, args: argparse.Namespace, times: List):
    if args.visualize:
        dot_file_dir = final_dir.joinpath("liveness")
        dot_file_dir.mkdir(exist_ok=True, parents=True)
    else:
        dot_file_dir = None

    x_preprocess = dtimer()
    tags_dict = preprocess_cfg(cfg, dot_file_dir, args)
    y_preprocess = dtimer()

    x = dtimer()
    init_time_liveness, end_time_liveness = layout_generation(cfg, args, final_dir.joinpath("stack_layouts"))
    y = dtimer()

    preprocess_time = (y_preprocess-x_preprocess)+(end_time_liveness-init_time_liveness)
    print("Preprocessing CFG: " + str(preprocess_time) + "s")
    times[2] += (preprocess_time)

    layout_time = (y-x)-(end_time_liveness-init_time_liveness)
    print("Layout generation: " + str(layout_time) + "s")
    times[3] += (layout_time)

    x = dtimer()
    needs_repair, _ = cfg_spec_ids(cfg, final_dir.joinpath("statistics.csv"), args.visualize)
    y = dtimer()

    print("Greedy algorithm: " + str(y - x) + "s")
    times[4] += (y - x)

    if args.sfs:
        sfs_from_cfg(cfg, final_dir)

    repair_time = 0
    # Only count time if repair is needed
    info_colouring = []
    if needs_repair:
        x = dtimer()
        info_colouring = repair_cfg(cfg, final_dir.joinpath("repair") if args.visualize else None)
        y = dtimer()
        repair_time = (y - x)
        times[4] += repair_time

    print("Repair algorithm: " + str(repair_time) + "s")

    if args.visualize:
        asm_code = final_dir.joinpath("asm")
        asm_code.mkdir(exist_ok=True, parents=True)
    else:
        asm_code = None

    x = dtimer()
    json_asm_contract = asm_from_cfg(cfg, tags_dict, args.source, asm_code, args.auxdata)
    y = dtimer()

    print("ASM generation: " + str(y - x) + "s")
    times[5] += (y - x)

    return json_asm_contract, info_colouring


# The Yul code refers to AST ids (e.g. object names such as Token_809, function names or the ids of the immutables),
# which differ between the copies of the same contract defined in several source files
AST_ID_SUFFIX_REGEX = re.compile(r"(?<=[A-Za-z0-9_$])_(\d+)(?!\d)")


def canonical_yul_cfg(yul_cfg: Yul_CFG_T) -> str:
    """
    Representation of a Yul CFG in which the AST ids are renamed consistently (in order of appearance), so that two
    copies of the same contract that only differ in the ids have the same representation
    """
    renaming = dict()

    def rename_ids(text: str) -> str:
        return AST_ID_SUFFIX_REGEX.sub(lambda match: f"_#{renaming.setdefault(match.group(1), len(renaming))}", text)

    def walk(node, immutable_ids: bool = False):
        if isinstance(node, dict):
            op = node.get("op")
            return {rename_ids(key): walk(value, key == "literalArgs" and op in ("setimmutable", "loadimmutable"))
                    for key, value in node.items()}
        elif isinstance(node, list):
            return [walk(value, immutable_ids) for value in node]
        elif isinstance(node, str):
            if immutable_ids and node.isdigit():
                return f"#{renaming.setdefault(node, len(renaming))}"
            return rename_ids(node)
        return node

    return json.dumps(walk(yul_cfg))


def find_contract_copies(json_dict: Dict[str, Yul_CFG_T]) -> Dict[str, str]:
    """
    Detects the contracts whose Yul CFGs only differ in the AST ids. Returns the representative (the first
    appearance) of each copy
    """
    representative = dict()
    copy_of = dict()
    for contract_name, yul_cfg in json_dict.items():
        canonical = canonical_yul_cfg(yul_cfg)
        if canonical in representative:
            copy_of[contract_name] = representative[canonical]
        else:
            representative[canonical] = contract_name
    return copy_of


def main(args):
    print("Grey Main")
    
    times = [0, 0, 0, 0, 0, 0, 0]

    x = dtimer()
    json_dict, settings = yul_cfg_dict_from_format(args.input_format, args.source,
                                                   args.contract, args.solc_executable)
    y = dtimer()
    times[0] += (y - x)

    print("Yul CFG Generation", y - x)

    # Copies of the same contract (e.g. flattened sources) are optimized once and their result is reused. The
    # contracts are still reported in their original order
    contract_order = list(json_dict.keys())
    copy_of = find_contract_copies(json_dict)
    for copy_name, contract_name in copy_of.items():
        print(f"Contract copy: {copy_name} -> {contract_name}")

    # Whether solc's block deduplicator runs on the generated assembly (used by the merging of equivalent blocks)
    args.solc_deduplicates = args.solc_dedup == "on" or \
        (args.solc_dedup == "auto" and importer_deduplicates_blocks(args.solc_executable))
    print("solc deduplicates the blocks of the assembly:", args.solc_deduplicates)

    final_dir = Path(args.folder)
    constants.DEBUG_DIR = final_dir.joinpath("debug")

    if constants.DEBUG:
        with open(debug_file('intermediate.json'), 'w') as f:
            json.dump(json_dict, f, indent=4)

    # The copies are not parsed nor optimized (the result of their representative is reused)
    json_dict = {contract_name: yul_cfg for contract_name, yul_cfg in json_dict.items()
                 if contract_name not in copy_of}

    x = dtimer()
    cfgs = parse_CFG_from_json_dict(json_dict, args.builtin)
    y = dtimer()

    print("CFG Parser: " + str(y - x) + "s")
    times[1] += (y - x)

    final_dir.mkdir(exist_ok=True, parents=True)
    asm_contracts = defaultdict(lambda: dict())
    asm_contracts_after_importer = defaultdict(lambda: dict())

    total_blocks_cfg = 0
    total_ins_cfg = 0

    contract_info = []
    call_freq = []
    info_repair = []
    # Results of each optimized contract, reused for its copies
    results = dict()
    for cfg_name in contract_order:
        if cfg_name in copy_of:
            asm_contract, importer_result = results[copy_of[cfg_name]]
            asm_contracts[cfg_name]["asm"] = asm_contract
            if not args.json_solc:
                print("Contract: " + cfg_name + " -> EVM Code: " + importer_result)
                contract_info.append({"contract": cfg_name, "bin_code": importer_result,
                                      "num_bytes": len(importer_result) // 2})
            else:
                contract_info.append({"contract": cfg_name, "bin_code": importer_result})
                asm_contracts_after_importer[cfg_name]["asm"] = asm_from_opcodes(importer_result)
            continue

        cfg = cfgs[cfg_name]
        blocks, ins = cfg.get_stats()
        
        total_blocks_cfg+=blocks
        total_ins_cfg += ins
        
        #      print("Synthesizing...", cfg_name)
        cfg_dir = final_dir.joinpath(cfg_name)
        asm_contract, info_repair_cfg = analyze_single_cfg(cfg, cfg_dir, args, times)
        for row in info_repair_cfg:
            row["contract"] = cfg_name
        info_repair.extend(info_repair_cfg)
        asm_contracts[cfg_name]["asm"] = asm_contract

        # Store the call info in a csv
        call_freq.extend(function_frequency(cfg, cfg_name))

        if args.visualize:
            assembly_path = store_asm_output(asm_contract, cfg_name, cfg_dir)

        std_assembly_path = store_asm_standard_json_output(asm_contract, cfg_name, cfg_dir, settings)
        # print(std_assembly_path)
        # synt_binary = SolidityCompilation.importer_assembly_file(assembly_path, solc_executable=args.solc_executable)

        x = dtimer()
        if not args.json_solc:
            synt_binary_stdjson = SolidityCompilation.importer_assembly_standard_json_file(std_assembly_path,
                                                                                           deployed_contract=cfg_name,
                                                                                           solc_executable=args.solc_executable)


            print("Contract: " + cfg_name + " -> EVM Code: " + synt_binary_stdjson)
            contract_info.append({"contract": cfg_name, "bin_code": synt_binary_stdjson,
                                   "num_bytes": len(synt_binary_stdjson) // 2})
            results[cfg_name] = (asm_contract, synt_binary_stdjson)

            if args.visualize:
                store_binary_output(cfg_name, synt_binary_stdjson, cfg_dir)

        else:
            synt_opcodes_stdjson = SolidityCompilation.importer_assembly_standard_json_file(std_assembly_path,
                                                                                            deployed_contract=cfg_name,
                                                                                            solc_executable=args.solc_executable,
                                                                                            selected_result="opcodes")
            contract_info.append({"contract": cfg_name, "bin_code": synt_opcodes_stdjson})

            asm_contracts_after_importer[cfg_name]["asm"] = asm_from_opcodes(synt_opcodes_stdjson)
            results[cfg_name] = (asm_contract, synt_opcodes_stdjson)

        y = dtimer()

        print("solc importer: " + str(y - x) + "s")
        times[6] += (y - x)

    times_str = map(lambda x: str(x), times)
    print("Times " + args.source + ": " + ",".join(times_str))
    print("Total times " + args.source +": "+ str(sum(times)))

    print("Total Blocks CFG "+ args.source +": "+str(total_blocks_cfg))
    print("Total Ins CFG "+ args.source +": "+str(total_ins_cfg))
    
    asm_combined_output = {"contracts": asm_contracts, "version": "grey"}

    pd.DataFrame(call_freq).to_csv(final_dir.joinpath(f"call_info_{Path(args.source).stem}.csv"))
    pd.DataFrame(info_repair).to_csv(final_dir.joinpath(f"repair_{Path(args.source).stem}.csv"))

    with open(str(final_dir.joinpath(Path(args.source).stem)) + "_bef_importer.json_solc", 'w') as f:
        json.dump(asm_combined_output, f, indent=4)

    # We store the combined output as well after the importer
    if args.json_solc:
        with open(str(final_dir.joinpath(Path(args.source).stem)) + "_aft_importer.json_solc", 'w') as f:
            json.dump({"contracts": asm_contracts_after_importer, "version": "grey"}, f, indent=4)

    pd.DataFrame(contract_info).to_csv(final_dir.joinpath(f"{Path(args.source).stem}.csv"))
