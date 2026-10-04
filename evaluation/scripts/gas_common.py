"""
Common utilities of the gas evaluation scripts (gas_semantic_tests.py, gas_mainnet_replay.py): number of jobs given
the load of the machine, a guard on the free disk space, and readers of the bytecodes kept by
`compare_variants.py --keep-artifacts`.

Artifacts of a run folder <results>/artifacts/:
  - <variant>/<run identifier>_d<depth>.tar.gz: grey's CSVs (column bin_code, creation code per contract) and the
    assembly given to the importer;
  - solc_<reference>/<run identifier>.json.gz: {"error": ..., "bytecodes": {contract: creation code or None}}.
The run identifier is `compare_repair_slots.run_identifier` of the input (source path, format, solc, contract).
"""

import gzip
import json
import math
import os
import shutil
import subprocess
import tarfile
import tempfile
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# The evaluation scripts (evaluation/scripts) use the comparison scripts shared with the other experiments
# (scripts/compare_*.py of the repository). On grey-remote both are copied to the same folder
REPOSITORY_SCRIPTS = Path(__file__).resolve().parent.parent.parent.joinpath("scripts")
if REPOSITORY_SCRIPTS.is_dir():
    sys.path.append(str(REPOSITORY_SCRIPTS))

from compare_repair_slots import input_format_from_extension, run_identifier
from compare_with_solc import METADATA_SETTINGS, grey_bytecodes


class NotEnoughDiskSpace(Exception):
    pass


def jobs_from_load(reserved_cores: int = 3, minimum_jobs: int = 4) -> int:
    """
    Cores that are not busy according to the 1-minute load, minus the reserved ones (at least minimum_jobs, as the
    run scripts on grey-remote: the machine is often oversubscribed by other users)
    """
    free_cores = os.cpu_count() - math.ceil(os.getloadavg()[0]) - reserved_cores
    return max(minimum_jobs, free_cores)


def ensure_free_space(path: Path, minimum_gb: float) -> None:
    """
    Raises NotEnoughDiskSpace if the file system of path has less than minimum_gb free
    """
    free_gb = shutil.disk_usage(path).free / 1e9
    if free_gb < minimum_gb:
        raise NotEnoughDiskSpace(f"{free_gb:.1f} GB free in {path} (minimum {minimum_gb} GB)")


def input_info_for(source: Path, solc_executable: Path) -> Dict:
    """
    The input description used by compare_variants.py for an input given with --inputs-from and --force-solc
    """
    return {"source": source.resolve(), "input_format": input_format_from_extension(source),
            "solc": solc_executable.resolve(), "contract": None}


def variant_creation_codes(artifacts_dir: Path, variant: str, input_info: Dict, depth: int = 16) \
        -> Optional[Dict[str, Optional[str]]]:
    """
    Creation code per contract name of a variant for the input (None if the artifact does not exist, i.e. the
    run failed). The variant is a folder of artifacts_dir or an absolute path to the artifacts folder of another
    run. Folders whose name starts with "solc_" are solc references; the rest are grey variants
    """
    identifier = run_identifier(input_info)
    if Path(variant).name.startswith("solc_"):
        artifact_file = artifacts_dir.joinpath(variant, f"{identifier}.json.gz")
        if not artifact_file.is_file():
            return None
        with gzip.open(artifact_file, "rt") as f:
            return json.load(f)["bytecodes"]
    artifact_file = artifacts_dir.joinpath(variant, f"{identifier}_d{depth}.tar.gz")
    if not artifact_file.is_file():
        return None
    with tempfile.TemporaryDirectory(prefix="gas_artifact_") as temporary_folder, \
            tarfile.open(artifact_file, "r:gz") as archive:
        csv_members = [member for member in archive.getmembers() if member.name.endswith(".csv")
                       and "/" not in member.name]
        archive.extractall(temporary_folder, members=csv_members, filter="data")
        return dict(grey_bytecodes(Path(temporary_folder)))


def intrinsic_calldata_gas(data: bytes, is_creation: bool) -> int:
    """
    Calldata part of the intrinsic gas of a transaction (EIP-2028: 16 per non-zero byte, 4 per zero byte), plus the
    initcode word cost of a creation (EIP-3860: 2 per 32-byte word). Ignores the EIP-7623 floor
    """
    zero_bytes = data.count(0)
    gas = 4 * zero_bytes + 16 * (len(data) - zero_bytes)
    if is_creation:
        gas += 2 * ((len(data) + 31) // 32)
    return gas


def _compile_deployed(standard_json: Dict, contract: str, solc_executable: Path, cwd: Path,
                      link_references: Optional[Dict] = None) \
        -> Tuple[Optional[str], Optional[str], Optional[Dict[str, List[Dict]]], str]:
    """
    Compiles a standard JSON input (a source or an assembly given to the importer) selecting the creation code, the
    deployed code and its immutable references, and returns those of the contract (None if not found or ambiguous)
    and the error. In the deployed code the immutables are zero: their values are written by the constructor. If
    link_references is given, it is filled with the library placeholders of the deployed code ({file: {library:
    [{start, length}]}})
    """
    selection = ["evm.bytecode.object", "evm.deployedBytecode.object", "evm.deployedBytecode.immutableReferences",
                 "evm.deployedBytecode.linkReferences"]
    standard_json["settings"]["outputSelection"] = {"*": {"*": selection, "": selection}}
    completed = subprocess.run([str(solc_executable), "--standard-json"], input=json.dumps(standard_json),
                               capture_output=True, text=True, cwd=cwd)
    output = json.loads(completed.stdout)
    found = [info["evm"] for file_contracts in output.get("contracts", {}).values()
             for name, info in file_contracts.items() if name in (contract, "")]
    if len(found) != 1:
        errors = "; ".join(error["formattedMessage"].splitlines()[0] for error in output.get("errors", [])
                           if error.get("severity") == "error")
        return None, None, None, f"{len(found)} contracts named {contract} {errors}".strip()
    evm = found[0]
    if link_references is not None:
        link_references.update(evm["deployedBytecode"].get("linkReferences") or {})
    return (evm["bytecode"]["object"], evm["deployedBytecode"]["object"],
            evm["deployedBytecode"]["immutableReferences"], "")


def _compile_immutable_references(standard_json: Dict, contract: str, solc_executable: Path, cwd: Path) \
        -> Tuple[Optional[Dict[str, List[Dict]]], Optional[str], str]:
    """
    The immutable references of the deployed code of the contract and its creation code (see _compile_deployed)
    """
    creation, _, references, error = _compile_deployed(standard_json, contract, solc_executable, cwd)
    return references, creation, error


SUBOBJECT_REFERENCES = ("PUSH [$]", "PUSH #[$]")
BLOCK_ENDS = {"JUMP", "JUMPI", "JUMPDEST", "tag", "STOP", "REVERT", "INVALID", "SELFDESTRUCT"}


def runtime_subobject_index(assembly: Dict) -> int:
    """
    Index of the sub-object of an assembly that is the deployed code: the one whose copy in the creation code ends in
    a RETURN (the others are copied for a CREATE/CREATE2, e.g. the ProxyAdmin that OpenZeppelin's
    TransparentUpgradeableProxy deploys in its constructor). The sub-objects of grey's assembly carry no names, and
    the importer always reports sub-object 0 as the deployed code. Defaults to 0
    """
    code = assembly[".code"]
    for position, item in enumerate(code):
        if item.get("name") != "PUSH [$]":
            continue
        for following in code[position + 1:]:
            name = following.get("name")
            if name == "RETURN":
                return int(item["value"], 16)
            if name in ("CREATE", "CREATE2") or name in BLOCK_ENDS:
                break
    return 0


def with_runtime_first(assembly: Dict, runtime_index: int) -> Dict:
    """
    A copy of the assembly with the sub-objects 0 and runtime_index swapped (and their references in the creation
    code renumbered), so that the importer reports the right deployed code
    """
    import copy
    swapped = copy.deepcopy(assembly)
    data = swapped[".data"]
    zero, other = "0", format(runtime_index, "x").upper()
    key_other = next(key for key in data if int(key, 16) == runtime_index)
    data["0"], data[key_other] = data[key_other], data["0"]
    width = None
    for item in swapped[".code"]:
        if item.get("name") in SUBOBJECT_REFERENCES:
            width = width or len(item["value"])
            index = int(item["value"], 16)
            if index in (0, runtime_index):
                item["value"] = format(runtime_index if index == 0 else 0, "x").upper().rjust(width, "0")
    return swapped


def link_libraries(code: str, link_references: Dict, libraries: Dict) -> Tuple[Optional[str], str]:
    """
    Writes the addresses of the input's libraries (settings.libraries: {file: {library: address}}) at the library
    placeholders of a code. The importer gives the references with upper-case names, so they are matched ignoring
    case. A library not found under its file is matched by its name alone, if no other library has that name: inputs
    can list them under the file that uses them (Rollup) or without a file (Etherscan's Library field). Returns the
    linked code (None if a library has no address) and the error
    """
    addresses = {(file.lower(), library.lower()): address.lower().removeprefix("0x")
                 for file, file_libraries in (libraries or {}).items() for library, address in file_libraries.items()}
    by_name: Dict[str, Optional[str]] = {}
    for (_, library), address in addresses.items():
        by_name[library] = address if by_name.get(library, address) == address else None
    for file, file_libraries in link_references.items():
        for library, references in file_libraries.items():
            address = addresses.get((file.lower(), library.lower())) or by_name.get(library.lower())
            if address is None:
                return None, f"no address for library {file}:{library}"
            for reference in references:
                start, length = 2 * reference["start"], 2 * reference["length"]
                code = code[:start] + address.rjust(length, "0") + code[start + length:]
    return code, ""


def variant_runtime_code(artifacts_dir: Path, variant: str, input_info: Dict, contract: str, solc_executable: Path,
                         depth: int = 16, extra_libraries: Optional[Dict] = None) \
        -> Tuple[Optional[str], Optional[Dict[str, List[Dict]]], str]:
    """
    Deployed code of a variant's contract (immutables zero) and its immutable references (decimal AST ids), and the
    error. grey: the assembly kept in the artifacts is imported again; solc: the input is compiled as
    compare_with_solc.solc_bytecodes does. In both cases the creation code must be the one of the artifacts. The
    library placeholders are linked with the input's settings.libraries plus extra_libraries ({file: {library:
    address}}, e.g. from Etherscan's Library field)
    """
    input_libraries = json.loads(Path(input_info["source"]).read_text()).get("settings", {}).get("libraries") or {}
    all_libraries = {**input_libraries, **{f"extra:{file}": libraries
                                           for file, libraries in (extra_libraries or {}).items()}}
    expected_code = (variant_creation_codes(artifacts_dir, variant, input_info, depth) or {}).get(contract)
    if expected_code is None:
        return None, None, "no code"
    if Path(variant).name.startswith("solc_"):
        standard_json = json.loads(Path(input_info["source"]).read_text())
        settings = standard_json.setdefault("settings", {})
        settings["viaIR"] = True
        settings.setdefault("optimizer", {})["enabled"] = True
        settings["metadata"] = dict(METADATA_SETTINGS)
        link_references = {}
        creation, runtime, references, error = _compile_deployed(standard_json, contract, solc_executable,
                                                                 Path(input_info["source"]).parent, link_references)
        # solc only links the libraries listed under the file that defines them: link the rest here, as for grey
        if runtime is not None and "__$" in runtime and link_references:
            runtime, error = link_libraries(runtime, link_references, all_libraries)
    else:
        artifact_file = artifacts_dir.joinpath(variant, f"{run_identifier(input_info)}_d{depth}.tar.gz")
        with tarfile.open(artifact_file, "r:gz") as archive:
            try:
                member = archive.getmember(f"{contract}/{contract}_standard_json_output.json")
            except KeyError:
                return None, None, "no assembly in the artifact"
            standard_json = json.load(archive.extractfile(member))
        link_references: Dict = {}
        creation, runtime, references, error = _compile_deployed(json.loads(json.dumps(standard_json)), contract,
                                                                 solc_executable, Path(tempfile.gettempdir()),
                                                                 link_references)
        # The importer reports sub-object 0 as the deployed code: import again with the runtime sub-object first
        # (the creation code was already checked against the artifact with the original order)
        source_name = next(iter(standard_json["sources"]))
        assembly = standard_json["sources"][source_name]["assemblyJson"]
        runtime_index = runtime_subobject_index(assembly) if assembly.get(".data") else 0
        if runtime is not None and runtime_index != 0:
            standard_json["sources"][source_name]["assemblyJson"] = with_runtime_first(assembly, runtime_index)
            link_references = {}
            _, runtime, references, error = _compile_deployed(standard_json, contract, solc_executable,
                                                              Path(tempfile.gettempdir()), link_references)
        # The importer ignores settings.libraries for an assembly: the placeholders are linked here with the addresses
        # of the input (solc links its own code with them)
        if runtime is not None and link_references:
            runtime, error = link_libraries(runtime, link_references, all_libraries)
        # The importer names the immutables by the hexadecimal AST id (solc and Sourcify use decimal ids)
        if references is not None:
            references = {str(int(identifier, 16)): value for identifier, value in references.items()}
    if runtime is None:
        return None, None, error
    if creation != expected_code:
        return None, None, "recompiled creation code differs from the artifact's"
    if "__$" in runtime:
        return None, None, "unlinked library (no address in the input's settings.libraries)"
    return runtime, references, ""


def variant_immutable_references(artifacts_dir: Path, variant: str, input_info: Dict, contract: str,
                                 solc_executable: Path, depth: int = 16) -> Tuple[Optional[Dict[str, List[Dict]]], str]:
    """
    Immutable references ({AST id: [{start, length}]}) of the deployed code of a variant's contract, and the error.
    grey: the assembly given to the importer (kept in the artifacts) is imported again selecting them; solc: the
    input is compiled as compare_with_solc.solc_bytecodes does. In both cases the creation code must be the one of
    the artifacts
    """
    expected_code = (variant_creation_codes(artifacts_dir, variant, input_info, depth) or {}).get(contract)
    if expected_code is None:
        return None, "no code"
    if Path(variant).name.startswith("solc_"):
        standard_json = json.loads(Path(input_info["source"]).read_text())
        settings = standard_json.setdefault("settings", {})
        settings["viaIR"] = True
        settings.setdefault("optimizer", {})["enabled"] = True
        settings["metadata"] = dict(METADATA_SETTINGS)
        references, code, error = _compile_immutable_references(standard_json, contract, solc_executable,
                                                                Path(input_info["source"]).parent)
    else:
        artifact_file = artifacts_dir.joinpath(variant, f"{run_identifier(input_info)}_d{depth}.tar.gz")
        with tarfile.open(artifact_file, "r:gz") as archive:
            try:
                member = archive.getmember(f"{contract}/{contract}_standard_json_output.json")
            except KeyError:
                return None, "no assembly in the artifact"
            standard_json = json.load(archive.extractfile(member))
        references, code, error = _compile_immutable_references(standard_json, contract, solc_executable,
                                                                Path(tempfile.gettempdir()))
        # The importer names the immutables by the hexadecimal AST id (solc and Sourcify use decimal ids)
        if references is not None:
            references = {str(int(identifier, 16)): value for identifier, value in references.items()}
    if references is None:
        return None, error
    if code != expected_code:
        return None, "recompiled creation code differs from the artifact's"
    return references, ""


def patch_immutables(runtime_code: str, references: Dict[str, List[Dict]], onchain_values: Dict[str, str]) \
        -> Tuple[Optional[str], int, str]:
    """
    Writes the on-chain values of the immutables (Sourcify's, keyed by the AST ids of the original compilation) into
    a runtime code at its immutable references (keyed by the AST ids of this compilation, decimal). The ids are the
    same when the sources are the same; otherwise (other compiler version or source order) they are assigned in source
    order, so both sets are matched in the order of their ids, provided the numbers are equal. Returns the patched
    code (None if they cannot be matched), the number of values that differed from the ones in the code (e.g.
    address(this) of a CREATE2 contract) and the error
    """
    if set(references) == set(onchain_values):
        ours = theirs = sorted(references, key=int)
    else:
        ours, theirs = sorted(references, key=int), sorted(onchain_values, key=int)
        if len(ours) != len(theirs):
            return None, 0, f"{len(ours)} immutables in the code, {len(theirs)} on chain"
    code = runtime_code.removeprefix("0x")
    changed = 0
    for our_id, their_id in zip(ours, theirs):
        value = onchain_values[their_id].removeprefix("0x").rjust(64, "0")
        for reference in references[our_id]:
            start, length = 2 * reference["start"], 2 * reference["length"]
            if code[start:start + length] != value[-length:]:
                changed += 1
            code = code[:start] + value[-length:] + code[start + length:]
    return "0x" + code, changed, ""
