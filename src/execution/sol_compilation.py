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
from typing import Dict, Any, Tuple, List, Optional
import tempfile


def run_command(cmd):
    print(cmd)
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


def process_sol_yul_cfg(compiler_output: str, deployed_contract: Optional[str]) -> Dict[str, Any]:
    """
    Given the compiler output, extracts the yul cfg JSON (format with only the yul JSON enabled)
    """
    # The yul_cfg information is preceded by no header, such as
    # Binary (for --bin), Contract JSON ABI (for --abi) or User Documentation (for --userdoc)
    # TODO: ask for a fix
    default_dict = dict()
    compiler_lines = compiler_output.splitlines()
    for compiler_line in compiler_lines:
        if compiler_line != "null":
            json_dict = json.loads(compiler_line)

            # For None contracts, we retrieve all the values
            if deployed_contract is None:
                default_dict.update(json_dict)
            # Search for the yul object that contains the contract as a key
            elif any(deployed_contract in contract for contract in json_dict.keys()):
                return json_dict

    if deployed_contract is not None:
        raise ValueError(f"{deployed_contract} not found in the compiler output")

    return default_dict


def process_sol_yul_cfg_multiple(compiler_output: str) -> Dict[str, Dict[str, Any]]:

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


class EtherscanCompilation:
    """
    Compiler from different files in Etherscan
    """

    def __init__(self, final_file: str, solc_command: str):
        self._final_file: Path = Path(final_file)
        self.flags: str = ""

        # Command to invoke the solc compiler
        self._solc_command: str = solc_command

        # TODO: decide how to represent via-ir
        self._via_ir = False
        self._yul_setting = False

    @staticmethod
    def from_single_solidity_code(sol_file: str, deployed_contract: Optional[str],
                                  final_file: str, solc_executable: str = "solc") -> Dict[str, Any]:
        """
        Compiles a single sol file
        """
        compilation = EtherscanCompilation(final_file, solc_executable)
        compilation.flags = "--yul-cfg-json --optimize"
        return compilation.compile_sol_file_from_code(sol_file, deployed_contract)

    @staticmethod
    def from_multi_sol(multi_sol_info: Dict[str, Any], deployed_contract: str,
                       final_file: str, solc_executable: str = "solc") -> Dict[str, Any]:
        """
        Compiles a file from the multi sol representation
        """
        compilation = EtherscanCompilation(final_file, solc_executable)
        compilation.flags = "--yul-cfg-json --optimize"
        return compilation.compile_multiple_sources(multi_sol_info, deployed_contract)

    @staticmethod
    def from_json_input(json_input: Dict[str, Any], deployed_contract: Optional[str], final_file: str,
                        solc_executable: str = "solc") -> Dict[str, Any]:
        """
        Compiles a file in the JSON input representation
        """
        compilation = EtherscanCompilation(final_file, solc_executable)
        compilation.flags = "--standard-json"
        return compilation.compile_json_input(json_input, deployed_contract)

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

    def _process_json_output(self, output_dict: Dict, error: str) -> bool:
        """
        Process the output generated from the json input
        """
        # Check no field errors appear when parsing as a json and one of the messages is indeed an error
        # (see https://docs.soliditylang.org/en/v0.8.17/using-the-compiler.html)
        if "errors" in output_dict and any(error_msg["severity"] == "error" for error_msg in output_dict["errors"]):
            logging.error(f"Errors: {output_dict['errors']}")
            return False
        else:
            if error != "":
                logging.warning(error)

            # Produce a json file for each contract
            for filename in output_dict["contracts"]:
                current_file = output_dict["contracts"][filename]
                for contract_name in current_file:
                    yul_cfg_current = current_file[contract_name]["yulCFGJson"]

                    if yul_cfg_current is not None:

                        # Store the output following the asm format
                        with open(self._final_file, 'w') as f:
                            json.dump(yul_cfg_current, f, indent=4)
        return True

    def compile_json_input(self, json_input: Dict, deployed_contract: Optional[str] = None) -> Optional[Dict[str, Any]]:
        # Change the settings from the json input
        json_input["settings"] = self._json_input_set_settings()

        # Compile in a given intermediate file
        fd, tmp_file = tempfile.mkstemp()

        with os.fdopen(fd, 'w') as f:
            # Write JSON in a file
            f.write(json.dumps(json_input))

        # Compile it using the corresponding options
        output_dict, error = self._compile_json_input(tmp_file)

        os.remove(tmp_file)
        # Then we process the output and generate the corresponding file
        correct_compilation = self._process_json_output(output_dict, error)

        if not correct_compilation:
            return None

        return output_dict

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
            with open(self._final_file, 'w') as f:
                f.write(output)
        return True

    def compile_single_sol_file(self, sol_file: str) -> Tuple[bool, str]:
        """
        Compiles a single sol file using the file name
        """
        sol_output, error = self._compile_sol_command(sol_file)
        correct_compilation = self._process_sol_command(sol_output, error)
        return correct_compilation, sol_output

    def compile_sol_file_from_code(self, source_code_plain: str, deployed_contract: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Compiles a single sol file from its textual representation and returns the output
        """
        fd, tmp_file = tempfile.mkstemp()
        with os.fdopen(fd, 'w') as f:
            f.write(source_code_plain)
        correct_compilation, output = self.compile_single_sol_file(tmp_file)
        os.remove(tmp_file)

        if not correct_compilation:
            return None

        return process_sol_yul_cfg(output, deployed_contract)

    def compile_multiple_sources(self, source_code_dict: Dict[str, Dict[str, str]],
                                 deployed_contract: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Computes multiple sol files using the multi file representation from Etherscan
        """
        tmp_dir = tempfile.mkdtemp()
        tmp_folder = Path(tmp_dir)

        main_sol_file = extract_files_from_multisol_repr(source_code_dict, tmp_folder, deployed_contract)

        # Change to the path in which we have generated the files
        old_path = os.getcwd()
        # Copies the executable in the corresponding folder (if it is indeed an executable)
        if Path(self._solc_command).is_file():
            shutil.copy(self._solc_command, tmp_folder)

        os.chdir(tmp_folder)
        output_sol, error = self._compile_sol_command(main_sol_file)
        os.chdir(old_path)

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
            return EtherscanCompilation.from_json_input(code_dict, main_contract, resulting_file, solc_executable)

        except Exception as e:
            try:
                code_dict = json.loads(source_code)
                logging.log(1, f"Multi sol input {address}")
                return EtherscanCompilation.from_multi_sol(code_dict, main_contract, resulting_file, solc_executable)

            except Exception as e:
                logging.log(1, f"Single sol input {address}")
                return EtherscanCompilation.from_single_solidity_code(source_code, main_contract, resulting_file, solc_executable)


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
