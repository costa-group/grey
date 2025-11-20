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
import tempfile
from pathlib import Path
from typing import Dict, Any, Tuple, List, Optional, Callable, Union
from global_params.types import Yul_CFG_T

headers = {"asm": "EVM assembly:", "bin": "Binary:", "yul": "Yul Control Flow Graph:"}


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
    pattern = re.compile("Version: ([0-9]+\.[0-9]+\.[0-9]+)")
    match = pattern.search(output_sol)
    if match is not None:
        return match.group(1)
    else:
        raise ValueError(f"{output_sol} does not contain solc version in proper format")


def change_pragma(initial_contract: str, pragma_name: str = "0.8.17"):
    pattern = re.compile("pragma solidity .*?;")
    contract_with_pragma = re.sub(pattern, f"pragma solidity ^{pragma_name};",initial_contract)
    return contract_with_pragma


def yul_close_compilation_settings() -> Dict:
    """
    Configuration to use in order test that the Yul code matches the one from the JSON representation
    """
    return {
            "enabled": True,
            "details": {
                "peephole": False,
                "inliner": False,
                "jumpdestRemover": False,
                "orderLiterals": False,
                "deduplicate": False,
                "cse": False,
                "constantOptimizer": False
            }
    }


def default_optimization_settings() -> Dict:
    """
    Default values for te optimizer field
    """
    return {"enabled": True}


def process_contract_output(contract_output: str, representations: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Processes the solc output from a single contract, extracting all representations
    """
    output_selection = representations if representations is not None else list(headers.keys())
    output_selection_dict = dict()
    for output in output_selection:
        info_re = re.compile(f"{headers[output]}\n(.*?)\n")
        info_match = re.search(info_re, contract_output)
        if info_match is not None:
            output_selection_dict[output] = info_match.group(1) if output == "bin" else json.loads(info_match.group(1))
        else:
            raise ValueError(f"{output} info is not found in contract output: {contract_output}")
    return output_selection_dict


def process_sol_output(compiler_output: str, representations: Optional[List[str]] = None) -> Dict[str, Dict[str, Any]]:
    """
    Given the compiler output from solc and (optionally) output representations, extracts the information
    of those output in a dict for every contract. If no output is specified, all the information possible is retrieved.
    This function assumes the compiler output has no pretty-json enabled.
    """
    assert all(output_repr in headers for output_repr in representations), \
        f"Unknown representation specified. Only {headers.keys()} are allowed"

    contract_header = r"\n======= (.*?) =======\n"
    split_representation = [output for output in re.split(contract_header, compiler_output)]

    # It returns first the contract name and then  the information
    # The first string is always empty, as the string starts with the pattern used for the split
    contracts_headers = [string for string in split_representation[1::2]]
    output_per_contract = [string for string in split_representation[2::2]]

    assert len(output_per_contract) == len(contracts_headers), f"Number of identified contracts " \
                                                               f"does not match the number of information processed"

    contract_information = dict()
    for output_contract, contract_name in zip(output_per_contract, contracts_headers):

        # Output contract can be empty for sol libraries and interfaces
        if output_contract != "":
            contract_information[contract_name] = process_contract_output(output_contract, representations)

    return contract_information


def process_sol_yul_cfg(compiler_output: str, deployed_contract: Optional[str]) -> Dict[str, Yul_CFG_T]:
    """
    DEPRECATED: old version of the yul cfg JSON output
    Given the compiler output, extracts the yul cfg JSON (format with only the yul JSON enabled)
    """
    # The yul_cfg information is preceded by no header, such as
    # Binary (for --bin), Contract JSON ABI (for --abi) or User Documentation (for --userdoc)

    default_dict = dict()
    compiler_lines = compiler_output.splitlines()
    for compiler_line in compiler_lines:
        if compiler_line != "null":
            json_dict = json.loads(compiler_line)

            # For None contracts, we retrieve all the values
            if deployed_contract is None:
                # Assume the json only contains two contracts: one for the deployment code
                # and the other with the runtime

                contract_name = [contract for contract in json_dict.keys() if "deployed" not in contract][0]
                default_dict[contract_name] = json_dict

            # Search for the yul object that contains the contract as a key
            elif any(deployed_contract in contract for contract in json_dict.keys()):
                return {deployed_contract: json_dict}

    if deployed_contract is not None:
        raise ValueError(f"{deployed_contract} not found in the compiler output")

    return default_dict


def process_sol_yul_cfg_multiple(compiler_output: str) -> Dict[str, Yul_CFG_T]:

    # For now, we assume only the yul cfg option is enabled
    yul_cfg_regex = r"\n======= (.*?) =======\n(.*?)\n"

    contracts = re.findall(yul_cfg_regex, compiler_output)

    contracts = {contract[0]: contract[1] for contract in contracts if contract[1]}
    if not contracts:
        logging.critical("Solidity compilation failed")

    return contracts


def extract_files_from_multisol_repr(source_code_dict: Dict[str, Dict[str, str]], folder: Path,
                                     deployed_contract: str) -> Path:
    """
    Extract the files from the multi-solidity representation in Etherscan and returns the name of the
    deployed contract
    """
    # Key: contract .sol file
    # Value: source code
    contract_to_compile = None
    for sol_file_name, sol_file_dict in source_code_dict.items():

        sol_file_contents = sol_file_dict["content"]
        sol_file = folder.joinpath(sol_file_name)
        with open(sol_file, 'w') as f:
            f.write(sol_file_contents)

        # Check main contract
        if f"contract {deployed_contract} " in sol_file_contents:
            if contract_to_compile is not None:
                logging.error(f"Contract {deployed_contract} appears in two files")
            contract_to_compile = Path(sol_file)

    if contract_to_compile is None:
        logging.error(f"Contract {deployed_contract} has not been found in any of the sol files")

    return contract_to_compile


def filter_information_from_contract(sol_output: str, deployed_contract: Optional[str],
                                     selected_header: str) -> Dict[str, Any]:
    """
    Returns a dict with all the information from the given header
    """
    output_dict = process_sol_output(sol_output, [selected_header])

    # We filter the corresponding contract
    if deployed_contract is not None:
        for deployed_filename, output_info in output_dict.items():
            if deployed_contract in deployed_filename and output_info[selected_header] is not None:
                return {deployed_contract: output_info[selected_header]}
    else:
        # Only return yul information
        return {contract_name: contract_info[selected_header] for contract_name, contract_info in
                output_dict.items()
                if contract_info[selected_header] is not None}


def process_importer_output(sol_output: str, deployed_contract: Optional[str], selected_header: str) -> str:
    """
    Given the compiler output from solc after the importer and (optionally) output representations, extracts the information
    of the corresponding contract (importer can only import one contract)
    """
    assert selected_header in headers, f"Unknown representation specified. Only {headers.keys()} are allowed"

    contract_header = r"Binary:\n(.*?)\n"
    return re.search(contract_header, sol_output).group(1)


def process_importer_standard_output(sol_output: str, deployed_contract: Optional[str], selected_header: str) -> str:
    """
    Given the compiler output from solc after the importer standard-json option, extracts the information
    of the corresponding contract (binary). selected_header can be either object (for the bytecode) or opcodes
    (for the bytecode in opcode format).
    """

    json_output = json.loads(sol_output)
    
    contracts = json_output["contracts"]
    assert deployed_contract in contracts, f"Contract {deployed_contract} not deployed"

    deployed_contract_info = contracts[deployed_contract][""]
    
    return deployed_contract_info["evm"]["bytecode"][selected_header]


class SolidityCompilation:
    """
    Compiler from different formats of the solc compiler that are also supported by Etherscan
    """

    def __init__(self, final_file: Optional[str], solc_command: str):
        self.CHANGE_SETTINGS = False
        self._final_file: Optional[Path] = Path(final_file) if final_file is not None else None
        self.flags: str = ""

        # Command to invoke the solc compiler
        self._solc_command: str = solc_command

        # TODO: decide how to represent via-ir
        self._via_ir = True
        self._yul_setting = False

        # Function to select the information from the contract
        self.process_output_function: Optional[Callable[[str, Optional[str], str], Union[Dict, str]]] = None

    @staticmethod
    def from_single_solidity_code(sol_file: str, deployed_contract: Optional[str] = None,
                                  final_file: Optional[str] = None, solc_executable: str = "solc") -> Optional[Dict[str, Yul_CFG_T]]:
        """
        Compiles a single sol file
        """
        compilation = SolidityCompilation(final_file, solc_executable)
        compilation.flags = "--yul-cfg-json --optimize"
        compilation.process_output_function = filter_information_from_contract
        return compilation.compile_single_sol_file(sol_file, deployed_contract)

    @staticmethod
    def importer_assembly_file(json_file: str, deployed_contract: Optional[str] = None,
                               final_file: Optional[str] = None, solc_executable: str = "solc"):
        compilation = SolidityCompilation(final_file, solc_executable)
        compilation.flags = "--import-asm-json --bin --optimize"
        compilation.process_output_function = process_importer_output
        return compilation.compile_single_sol_file(json_file, deployed_contract, "bin")

    @staticmethod
    def importer_assembly_standard_json_file(json_file: str, deployed_contract: Optional[str] = None,
                               final_file: Optional[str] = None, solc_executable: str = "solc", selected_result: str = "object"):
        # The selected result can be either an object or the list of opcodes
        compilation = SolidityCompilation(final_file, solc_executable)
        compilation.flags = "--standard-json"
        compilation.process_output_function = process_importer_standard_output
        return compilation.compile_single_sol_file(json_file, deployed_contract, selected_result)

    @staticmethod
    def from_multi_sol(multi_sol_info: Dict[str, Any], deployed_contract: str,
                       final_file: Optional[str] = None, solc_executable: str = "solc") -> Optional[Dict[str, Yul_CFG_T]]:
        """
        Compiles a file from the multi sol representation
        """
        compilation = SolidityCompilation(final_file, solc_executable)
        compilation.flags = "--yul-cfg-json --optimize"
        compilation.process_output_function = filter_information_from_contract
        return compilation.compile_multiple_sources(multi_sol_info, deployed_contract)

    @staticmethod
    def from_json_input(json_input: Dict[str, Any], deployed_contract: Optional[str] = None, final_file: Optional[str] = None,
                        solc_executable: str = "solc", original_folder: Optional[str] = None) -> Optional[Dict[str, Yul_CFG_T]]:
        """
        Compiles a file in the JSON input representation
        """
        compilation = SolidityCompilation(final_file, solc_executable)
        compilation.flags = "--standard-json"
        return compilation.compile_json_input(json_input, deployed_contract, json_folder=original_folder)

    def _json_optimization_settings(self) -> Dict[str, Any]:
        """
        Sets the optimization settings for input json compilation
        """
        # TODO: decide how to decide which settings are enabled
        return yul_close_compilation_settings() if True else default_optimization_settings()

    def _json_output_selection(self) -> Dict[str, Any]:
        """
        Sets which output settings are generated for input json compilation
        """
        # For now, we just return the yul CFG JSON
        return {'*': {'*': ['yulCFGJson']}}

    def _json_input_set_settings(self) -> Dict[str, Any]:
        """
        Returns the settings field for the input json compilation
        """

        optimization_settings = self._json_optimization_settings()

        # Output selection is legacyAssembly
        output_selection = self._json_output_selection()

        settings = dict()

        settings["optimizer"] = optimization_settings
        settings["outputSelection"] = output_selection

        if self._via_ir:
            settings["viaIR"] = True

        return settings

    def _compile_json_input(self, json_file: str) -> Tuple[Dict, str]:
        command = f"{self._solc_command} {self.flags} {json_file}"
        output, error = run_command(command)
        output_dict = json.loads(output)
        return output_dict, error

    def _process_json_output(self, output_dict: Dict, error: str, deployed_contract: Optional[str]) -> Tuple[bool, Dict[str, Yul_CFG_T]]:
        """
        Process the output generated from the json input and returns a dict for each yul file
        """
        # Check no field errors appear when parsing as a json and one of the messages is indeed an error
        # (see https://docs.soliditylang.org/en/v0.8.17/using-the-compiler.html)
        if "errors" in output_dict and any(error_msg["severity"] == "error" for error_msg in output_dict["errors"]):
            logging.error(f"Errors: {output_dict['errors']}")
            return False, dict()
        else:
            if error != "":
                logging.warning(error)

            json_dict = dict()
            # Produce a json file for each contract
            for filename in output_dict["contracts"]:
                current_file = output_dict["contracts"][filename]
                for contract_name in current_file:
                    yul_cfg_current = current_file[contract_name]["yulCFGJson"]

                    if yul_cfg_current is not None:
                        json_dict[contract_name] = yul_cfg_current
                        # Only store the contract that matches the specification
                        if self._final_file is not None and deployed_contract is not None \
                                and contract_name == deployed_contract:

                            # Store the output following the asm format
                            with open(self._final_file, 'w') as f:
                                json.dump(yul_cfg_current, f, indent=4)
        return True, json_dict

    def compile_json_input(self, json_input: Dict, deployed_contract: Optional[str] = None,
                           json_folder: Optional[str] = None) -> Optional[Dict[str, Yul_CFG_T]]:
        # Change the settings from the json input
        if self.CHANGE_SETTINGS:
            json_input["settings"] = self._json_input_set_settings()
        else:
            json_input["settings"]["outputSelection"] = {'*': {'*': ['yulCFGJson']}}

        json_input["settings"]["metadata"] = {}
        json_input["settings"]["metadata"]["appendCBOR"] = False
        json_input["settings"]["metadata"]["useLiteralContent"] = False
        json_input["settings"]["metadata"]["bytecodeHash"] = "none"

        # If the folder is not None, then we first change the path
        if json_folder is not None:
            self._change_path_for_compilation(json_folder)

        # Compile in a given intermediate file
        fd, tmp_file = tempfile.mkstemp()

        with os.fdopen(fd, 'w') as f:
            # Write JSON in a file
            f.write(json.dumps(json_input))

        # Compile it using the corresponding options
        output_dict, error = self._compile_json_input(tmp_file)

        os.remove(tmp_file)

        # We restore the file afterward
        if json_folder is not None:
            self._restore_path_for_compilation()

        # Then we process the output and generate the corresponding file
        correct_compilation, yul_cfg_dict = self._process_json_output(output_dict, error, deployed_contract)

        if not correct_compilation:
            return None

        return yul_cfg_dict

    # Methods for compiling using the command line
    def _compile_sol_command(self, sol_file: str):
        command = f"{self._solc_command} {self.flags} {sol_file}"
        output, error = run_command(command)
        return output, error

    def _process_sol_command(self, output: str, error: str) -> bool:
        if "Error:" in error:
            logging.error(f"Errors compiling contract: {error}")
            return False
        else:
            if error != "":
                logging.warning(f"Warning in Contract")
                logging.warning(error)
            if self._final_file is not None:
                with open(self._final_file, 'w') as f:
                    f.write(output)
        return True

    def _change_path_for_compilation(self, new_path: str):
        """
        Changes the path for compiling from the corresponding folder
        """
        self._old_path = os.getcwd()

        # If solc is an executable, then we need to change the command to invoke it
        if Path(self._solc_command).is_file():
            self._old_solc_command = self._solc_command
            # The new solc command is invoked from the old path
            self._solc_command = Path(self._old_path).joinpath(self._solc_command).resolve()

        # Finally, we change the new path
        os.chdir(new_path)


    def _restore_path_for_compilation(self):
        """
        Restores the path for compilation after having changed it
        """
        # We restore the path and the solc command
        os.chdir(self._old_path)
        self._solc_command = self._old_solc_command

    def compile_single_sol_file(self, sol_file: str,
                                deployed_contract: Optional[str] = None,
                                selected_header: str = "yul") -> Optional[Dict[str, Any]]:
        """
        Compiles a single sol file using the file name and retrieves the information from a selected header
        """
        # Change to the path in which we have generated the files
        sol_folder = str(Path(sol_file).parent)
        self._change_path_for_compilation(sol_folder)

        # As we have moved the executable to the corresponding folder, we just need to pass the file name with
        # no parents dir
        sol_output, error = self._compile_sol_command(Path(sol_file).name)

        # After the compilation, we restore the path
        self._restore_path_for_compilation()

        correct_compilation = self._process_sol_command(sol_output, error)

        if not correct_compilation:
            return None

        return self.process_output_function(sol_output, deployed_contract, selected_header)

    def compile_sol_file_from_code(self, source_code_plain: str, deployed_contract: Optional[str] = None) -> Optional[Dict[str, Yul_CFG_T]]:
        """
        Compiles a single sol file from its textual representation and returns the output
        """
        fd, tmp_file = tempfile.mkstemp()
        with os.fdopen(fd, 'w') as f:
            f.write(source_code_plain)
        solution = self.compile_single_sol_file(tmp_file, deployed_contract)
        os.remove(tmp_file)

        return solution

    def compile_multiple_sources(self, source_code_dict: Dict[str, Dict[str, str]],
                                 deployed_contract: Optional[str] = None) -> Optional[Dict[str, Yul_CFG_T]]:
        """
        Computes multiple sol files using the multi file representation from Etherscan
        """
        tmp_dir = tempfile.mkdtemp()
        tmp_folder = Path(tmp_dir)

        main_sol_file = extract_files_from_multisol_repr(source_code_dict, tmp_folder, deployed_contract)

        self._change_path_for_compilation(str(tmp_folder))
        output_sol, error = self._compile_sol_command(main_sol_file)
        self._restore_path_for_compilation()

        shutil.rmtree(tmp_dir)
        # print(command)
        correct_compilation = self._process_sol_command(output_sol, error)

        if not correct_compilation:
            return dict()

        return process_sol_yul_cfg(output_sol, deployed_contract)


def extract_info_from_etherscan(etherscan_info: List[Dict]) -> List[Dict]:
    """
    Extracts a list with all the relevant information parsed in a format
    """
    info_list = []
    for etherscan_subinfo in etherscan_info:
        compiler_version = etherscan_subinfo["CompilerVersion"]
        source_code = etherscan_subinfo["SourceCode"]
        main_contract = etherscan_subinfo["ContractName"]
        is_optimized = int(etherscan_subinfo["OptimizationUsed"]) == 1
        n_runs = int(etherscan_subinfo["Runs"])
        info_list.append({"source_code": source_code, "main_contract": main_contract,
                          "compiler_version": compiler_version, "is_optimized": is_optimized, "n_runs": n_runs})
    return info_list


def compile_from_etherscan_json(etherscan_info: List[Dict], resulting_file: Path, address: str,
                                solc_executable: str = "solc") -> Optional[Dict[str, Any]]:
    """
    Given a file in etherscan format, compiles it in any of the three formats
    and returns the generated output as a dict with a key for each contract.
    If the compilation failed, returns None
    """
    # Skip if version <= 0.8.*
    etherscan_dict = extract_info_from_etherscan(etherscan_info)
    for etherscan_info in etherscan_dict:

        compiler_version = etherscan_info["compiler_version"]
        if "v0.8" not in compiler_version:
            logging.log(1, f"Skipped {address}. Compiler version: {compiler_version}")
            return dict()

        version_output, _ = run_command(f"{solc_executable} --version")
        version_to_optimize = extract_version_from_output(version_output)

        # Decrease in one the version to optimize for nightly builds, as
        # it fails otherwise
        if "-ci" in version_output:
            version_to_optimize = version_to_optimize[:-1] + str(int(version_to_optimize[-1]) - 1)

        source_code = change_pragma(etherscan_info["source_code"], version_to_optimize)
        main_contract = etherscan_info["main_contract"]
        try:
            code_dict = json.loads(source_code[1:-1])
            logging.log(1, f"Json input {address}")
            return SolidityCompilation.from_json_input(code_dict, main_contract, resulting_file, solc_executable)

        except Exception as e:
            try:
                code_dict = json.loads(source_code)
                logging.log(1, f"Multi sol input {address}")
                return SolidityCompilation.from_multi_sol(code_dict, main_contract, resulting_file, solc_executable)

            except Exception as e:
                logging.log(1, f"Single sol input {address}")
                return SolidityCompilation.from_single_solidity_code(source_code, main_contract, resulting_file, solc_executable)


def compile_files_from_folders(initial_folder: Path, final_folder: Path, solc_executable: str = "solc") -> None:
    """
    Compiles all the Etherscan JSON files in the initial folder and stores the compiled result in the final folder
    """
    final_folder.mkdir(parents=True, exist_ok=True)

    for i, etherscan_json_file in enumerate(glob.glob(str(initial_folder.joinpath("*.json")))):
        address = Path(Path(etherscan_json_file).name).stem

        # Load file
        with open(etherscan_json_file, 'r') as f:
            etherscan_info = json.load(f)

        filename = final_folder.joinpath(f"{address}.yul")
        compile_from_etherscan_json(etherscan_info, filename, address, solc_executable)


if __name__ == "__main__":
    logging.basicConfig(level=1)
    initial_dir, final_dir = Path(sys.argv[1]), Path(sys.argv[2])
    compile_files_from_folders(initial_dir, final_dir, "./solc-12-08")
