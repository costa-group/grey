"""
Module that contains the methods for reconstructing the bytecode in different formats
"""
import json
from typing import Dict, Any, List, Optional, Union, Iterable, Tuple
from solution_generation.utils import to_hex_default
from global_params.types import SMS_T, ASM_bytecode_T, ASM_contract_T, block_id_T, function_name_T
from parser.cfg import CFG
from parser.cfg_object import CFGObject
from parser.cfg_function import CFGFunction
from parser.cfg_block_list import CFGBlockList
from parser.cfg_block import CFGBlock
from parser.cfg_instruction import CFGInstruction
from cfg_methods.jump_insertion import tag_from_tag_dict
from pathlib import Path
import networkx as nx


# Solution ids to EVM assembly


def asm_from_op_info(op: str, value: Optional[Union[int, str]] = None,
                     jump_type: Optional[str] = None, source: Optional[int] = -1) -> ASM_bytecode_T:
    """
    JSON asm initialized with default values
    """
    
    default_asm = {"name": op, "begin": -1, "end": -1, "source": source}

    if value is not None:
        default_asm["value"] = str(value).upper()

    if jump_type is not None:
        default_asm["jumpType"] = jump_type

    return default_asm


def id_to_asm_bytecode(uf_instrs: Dict[str, Dict[str, Any]], instr_id: str) -> ASM_bytecode_T:
    """
    Given the dictionary of instructions in a SMS and an id, generates the corresponding ASM JSON
    """
    if instr_id in uf_instrs:
        associated_instr = uf_instrs[instr_id]

        # Special case: reconstructing PUSH0 (see sfs_generator/parser_asm.py)
        if associated_instr["disasm"] == "PUSH0":
            return asm_from_op_info("PUSH", "0")
        # Special PUSH cases that were transformed to decimal are analyzed separately
        elif associated_instr['disasm'] == "PUSH" or associated_instr['disasm'] == "PUSH data" \
                or associated_instr['disasm'] == "PUSHIMMUTABLE" or associated_instr['disasm'] == "ASSIGNIMMUTABLE":
            value = to_hex_default(associated_instr['value'][0])
            return asm_from_op_info(associated_instr['disasm'], value)
        elif associated_instr["disasm"] == "PUSH [TAG]":
            value = int(associated_instr["outpt_sk"][0])
            return asm_from_op_info("PUSH [tag]", value)
        else:
            return asm_from_op_info(associated_instr['disasm'],
                                    None if 'value' not in associated_instr else associated_instr['value'][0])

    else:
        # The id is the instruction itself (SWAPx, DUPx, ...)
        return asm_from_op_info(instr_id)


def id_seq_to_asm_bytecode(uf_instrs: Dict[str, Dict[str, Any]], id_seq: List[str]) -> List[ASM_bytecode_T]:
    """
    Converts a sequence of ids from the greedy algorithm to assembly bytecode
    """
    return [id_to_asm_bytecode(uf_instrs, instr_id) for instr_id in id_seq if instr_id != 'NOP']


def asm_from_ids(sms: SMS_T, id_seq: List[str]) -> List[ASM_bytecode_T]:
    """
    Converts the result from the greedy algorithm and the block specification into a list of JSON asm opcodes
    """
    instr_id_to_instr = {instr['id']: instr for instr in sms['user_instrs']}
    return id_seq_to_asm_bytecode(instr_id_to_instr, id_seq)


def asm_for_split_instruction(split_ins: CFGInstruction, function_name2entry: Dict[block_id_T, block_id_T]) -> List[ASM_bytecode_T]:
    """
    Reconstructs the assembly from a block with a single split instruction. If the split instruction is a
    function invocation, then it replaces it by the corresponding JUMP instruction
    """
    entry_block = function_name2entry.get(split_ins.get_op_name(), None)
    if entry_block is not None:
        # Introduces two tags: one for jumping to the instruction and one for returning.
        # Afterwards, introduce a JUMP instruction to invoke the function
        asm_ins = asm_from_op_info("JUMP", jump_type="[in]")

        asm_subblock = [asm_ins]

    elif split_ins.get_op_name() == "functionReturn":
        # For function returns, we replace them by a JUMP instruction
        asm_subblock = [asm_from_op_info("JUMP", jump_type="[out]")]

    elif split_ins.get_op_name().startswith("verbatim"):
        asm_subblock =[asm_from_op_info("VERBATIM", 0)] #WARNING: Value assigned to verbatim is 0

    elif split_ins.get_op_name().startswith("assignimmutable"):
        literal_args = split_ins.get_literal_args()
        value = to_hex_default(literal_args[0])
        asm_subblock = [asm_from_op_info(split_ins.get_op_name().upper(), value if literal_args is not None and len(literal_args) > 0 else None)]

    else:
        # Just include the corresponding instruction and the value field for builtin translations
        literal_args = split_ins.get_literal_args()
        asm_subblock = [asm_from_op_info(split_ins.get_op_name().upper(), literal_args[0] if literal_args is not None and
                                                                                       len(literal_args) > 0 else None)]
    return asm_subblock


def generate_asm_split_blocks(init_block_id: block_id_T, blocks: Dict[block_id_T, CFGBlock], tags_dict: Dict[block_id_T, int],
                              function_name2entry: Dict[function_name_T, block_id_T]) -> Tuple[CFGBlock, List[ASM_bytecode_T]]:
    """
    Joins all the instructions inside the sub blocks until we reach a function call or all sub blocks are combined.
    """
    asm_block = []

    block = blocks[init_block_id]

    jump_type = block.get_jump_type()
    is_function_call = block.split_instruction.op in function_name2entry
    while jump_type == "sub_block" and not is_function_call:

        if jump_type == "sub_block":
            asm_subblock = asm_from_ids(block.spec, block.greedy_ids)
            assert block.split_instruction is not None, \
                f"[ERROR]: Block {block.block_id} split_instructions has to contain a value in a subblock"
            asm_last = asm_for_split_instruction(block.split_instruction, function_name2entry)

        else:
            raise Exception("[ERROR]: Jump type can only be sub_block")

        asm_block += asm_subblock + asm_last
        block_id = block.get_falls_to()
        block = blocks[block_id]

        jump_type = block.get_jump_type()
        is_function_call = block.split_instruction.op in function_name2entry

    # We translate the last block
    asm_subblock = asm_from_ids(block.spec, block.greedy_ids)

    # Split instruction contains both jumps and not handled instructions
    if block.split_instruction is not None:
        asm_last = asm_for_split_instruction(block.split_instruction, function_name2entry)
    else:
        asm_last = []

    asm_block += asm_subblock + asm_last
    return block, asm_block


def locate_fallsto_block(block_id, fallsto_block, pos_dict, visited, asm_instructions, asm_block, pending_blocks):
    fallsto_id = fallsto_block.get_block_id()
    try:
        # It means that the block has been analyzed previously
        pos = pos_dict.index(fallsto_id)
        assert fallsto_id in visited, \
            "[ERROR]: Falls_to block should be in visited list when generating asm output"

        asm_instructions = asm_instructions[:pos] + asm_block + asm_instructions[pos:]
        pos_dict = pos_dict[:pos] + [block_id] * len(asm_block) + pos_dict[pos:]

    except ValueError:
        asm_instructions += asm_block
        pos_dict += [block_id] * len(asm_block)

        pending_blocks.append(fallsto_block)

    return pos_dict, asm_instructions


def generate_function_name2entry(functions: Iterable[CFGFunction]) -> Dict[function_name_T, block_id_T]:
    """
    Links each function name to its initial block
    """
    return {function.name: function.blocks.start_block for function in functions}


def traverse_cfg_block_list(block_list: CFGBlockList, function_name2entry: Dict[function_name_T, block_id_T],
                            tags_dict: Dict[block_id_T, int], asm_dir: Optional[Path] = None) -> List[ASM_bytecode_T]:
    """
    Traverses the blocks in the block list to generate the serialized assembly code
    """
    blocks = block_list.get_blocks_dict()

    init_block = blocks[block_list.start_block]
    assert (init_block.get_block_id().find("Block0") != -1)

    pending_blocks = [init_block]
    visited = []

    # It is used to know where we have to insert the asm instructions when we have a falls_to
    # It simulates the asm_instructions list with the identifiers of the blocks
    init_pos_dict = []

    asm_instructions = []
    graph = nx.DiGraph()
    relabel_dict = dict()

    while pending_blocks:
        next_block = pending_blocks.pop()

        block_id = next_block.get_block_id()
        visited.append(block_id)
        
        asm_index = len(asm_instructions)

        # If the block has been split we regenerate the whole block together
        # next block contains the last block of the sequence
        if next_block.get_jump_type() in ["sub_block"]:
            next_block, asm_block = generate_asm_split_blocks(block_id, blocks, tags_dict, function_name2entry)
        else:
            asm_block = asm_from_ids(next_block.spec, next_block.greedy_ids)
            
            if next_block.split_instruction is not None:
                asm_last = asm_for_split_instruction(next_block.split_instruction, function_name2entry)
            else:
                # if it is a falls_to or terminal split_instruction is None
                # Otherwise it is jump or jumpi
                asm_last = []

            if asm_block == [] and next_block.get_jump_type() == "terminal":

                assert len(next_block.get_instructions()) == 1, f"Falla { next_block.get_instructions()}"
                ins = next_block.get_instructions()[0]

                # Terminal blocks might contain calls to terminal functions (i.e. not so terminal...)
                asm_block = asm_for_split_instruction(ins, function_name2entry)

                if ins == next_block.split_instruction:
                    asm_block = []

            asm_block += asm_last

        if block_id in tags_dict:
            tag_asm = asm_from_op_info("tag", str(tags_dict[block_id]))
            jumpdest_asm = asm_from_op_info("JUMPDEST")
            asm_block = [tag_asm, jumpdest_asm] + asm_block

        jump_type = next_block.get_jump_type()
        falls_to, jump_to = None, None
        if jump_type == "conditional":

            jump_to = next_block.get_jump_to()
            falls_to = next_block.get_falls_to()

            if falls_to not in blocks or jump_to not in blocks:
                raise Exception("[ERROR]:...")

            if jump_to not in visited:
                pending_blocks.append(blocks[jump_to])

            # It checks if falls_to is in visited or not
            init_pos_dict, asm_instructions = locate_fallsto_block(block_id, blocks[falls_to], init_pos_dict, visited,
                                                                   asm_instructions, asm_block, pending_blocks)

        elif jump_type == "unconditional":
            asm_instructions += asm_block
            init_pos_dict += [block_id] * len(asm_block)

            jump_to = next_block.get_jump_to()

            if jump_to not in blocks:
                raise Exception("[ERROR]:...")

            if jump_to not in visited:
                pending_blocks.append(blocks[jump_to])

        elif jump_type == "falls_to" or jump_type == "sub_block":
            # Sub blocks now also fail into this case
            falls_to = next_block.get_falls_to()
            init_pos_dict, asm_instructions = locate_fallsto_block(block_id, blocks[falls_to], init_pos_dict, visited,
                                                                   asm_instructions, asm_block, pending_blocks)

        elif jump_type == "terminal" or jump_type == "FunctionReturn":

            asm_instructions += asm_block
            init_pos_dict += [block_id] * len(asm_block)

        elif jump_type == "mainExit":
            asm_instructions += asm_block + [asm_from_op_info("STOP")]
            init_pos_dict += [block_id] * (len(asm_block) + 1)

        else:
            raise Exception("[ERROR]: Unknown jump type when generating asm output")

        visited.append(block_id)

        if asm_dir is not None:
            if falls_to is not None:
                graph.add_node(falls_to)
                graph.add_edge(block_id, falls_to)

            if jump_to is not None:
                graph.add_node(jump_to)
                graph.add_edge(block_id, jump_to)

            relabel_dict[block_id] = '\n'.join([block_id] +
                                               [' '.join([instruction["name"], instruction.get("value", '')])
                                                for instruction in asm_instructions[asm_index:]])

    if asm_dir is not None:
        renamed_digraph = nx.relabel_nodes(graph, relabel_dict)
        nx.nx_agraph.write_dot(renamed_digraph, asm_dir.joinpath(block_list.name + ".dot"))

    return asm_instructions


def traverse_cfg(cfg_object: CFGObject, tags_dict: Dict[block_id_T, int], asm_dir: Optional[Path] = None) -> List[ASM_bytecode_T]:
    """
    Traverses the blocks in the CFG to generate the serialized assembly code
    """
    function_name2entry = generate_function_name2entry(cfg_object.functions.values())
    object_code = traverse_cfg_block_list(cfg_object.blocks, function_name2entry, tags_dict, asm_dir)

    function_code_list = []
    # TODO: devise better strategies to decide in which order the functions are included in the code
    for function_name, function in cfg_object.functions.items():
        function_code_list.extend(traverse_cfg_block_list(function.blocks, function_name2entry, tags_dict, asm_dir))
    return object_code + function_code_list


def recursive_asm_from_cfg_object(cfg_object: CFGObject, tags_dict: Dict, asm_dir: Optional[Path] = None, auxdata: Optional[bool] = False) -> ASM_contract_T:
    """
    Returns the level of the form {.code: ..., .auxdata: ..., [.data: ...]}
    """
    # Represents the structure
    tags = tags_dict[cfg_object.name]
    asm = traverse_cfg(cfg_object, tags, asm_dir)

    # 83 bytes of 0 + 0053 in CBOR encoding (see https://playground.sourcify.dev/)
    if auxdata:
        aux_data = "00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000053"
        current_object_json = {".code": asm, ".auxdata": aux_data}
    else:
        current_object_json = {".code": asm}
    
    sub_object = cfg_object.get_subobject()
    if sub_object is not None:
        json_asm_subobjects = recursive_asm_from_cfg(sub_object, tags_dict, asm_dir, auxdata)
        current_object_json[".data"] = {}
        for i, json_asm_subobject in enumerate(json_asm_subobjects):
            current_object_json[".data"][hex(i)[2:]] = json_asm_subobject
        
    return current_object_json


def recursive_asm_from_cfg(cfg: CFG, tags_dict: Dict, asm_dir: Optional[Path] = None, auxdata: Optional[bool] = False) -> List[ASM_contract_T]:
    """
    Returns the level of the form [{.code: ..., .auxdata: ..., [.data: ...]}]. This is later passed to the data object
    """

    multiple_object_json = []
    for obj_name, obj in cfg.get_objects().items():
        multiple_object_json.append(recursive_asm_from_cfg_object(obj, tags_dict, asm_dir, auxdata))

    return multiple_object_json


def asm_from_cfg(cfg: CFG, tags_dict: Dict, filename: str, final_path: Optional[Path] = None, auxdata: Optional[bool]  = False) -> ASM_contract_T:
    """
    Generates an assembly JSON from a CFG structure and the results of the optimization
    """
    #We have to access index 0 (there is only one contract at root level)
    asm_json = recursive_asm_from_cfg(cfg, tags_dict, final_path, auxdata)[0]
    if auxdata:
        asm_json.pop(".auxdata")
    asm_json["sourceList"] = [filename]

    return asm_json


def store_asm_output(json_object: Dict[str, Any], object_name: str, cfg_dir: Path) -> Path:
    file_to_store = cfg_dir.joinpath(object_name + "_asm.json")
    with open(file_to_store, 'w') as f:
        json.dump(json_object, f, indent=4)
    return file_to_store

def store_asm_standard_json_output(json_object: Dict[str, Any], object_name: str, cfg_dir: Path, settings_opt : Dict[str, Any] = {}) -> Path:
    file_to_store = cfg_dir.joinpath(object_name + "_standard_json_output.json")
    output_file = build_standard_json_output(json_object, object_name, settings_opt)

    with open(file_to_store, 'w') as f:
        json.dump(output_file, f, indent=4)
    return file_to_store

def store_binary_output(object_name: str, evm_code: str, cfg_dir: Path) -> None:
    file_to_store = cfg_dir.joinpath(object_name + "_bin.evm")
    with open(file_to_store, 'w') as f:
        f.write(evm_code)


def build_standard_json_output(json_object: Dict[str, Any], object_name : str, settings: Dict[str, Any]) -> Dict[str,Any]:
    output = {}
    
    output["language"] = "EVMAssembly"
    build_standard_json_settings(output,settings)

    output["sources"] = {}
    output["sources"][object_name] = {}
    output["sources"][object_name]["assemblyJson"] = json_object

    
    return output
    
def build_standard_json_settings(output_json, settings_opt):
    output_json["settings"] = {}
    
    if settings_opt == {}:
        opt_config = build_optimizer_configuration()
        output_json["settings"]["optimizer"] = opt_config

        output_json["settings"]["viaIR"] = True
        output_json["settings"]["metadata"] = {}
        output_json["settings"]["metadata"]["appendCBOR"] = False

    else:

        #Options not supported by the importer
        settings_opt.pop("compilationTarget", None)
        if "metadata" in settings_opt:
            settings_opt["metadata"].pop("bytecodeHash", None)
    
        output_json["settings"] = settings_opt

    # opt = output_json["settings"].get("optimizer",{})

    # opt_details = opt.get("details",{})
    # opt_details["cse"] = False
    # opt["details"] = opt_details
    
    # output_json["settings"]["optimizer"] = opt
    
    output = build_output_selection()
    output_json["settings"]["outputSelection"] = output
    
def build_output_selection():
    output_selection = {}
    output_selection["*"] = {}
    output_selection["*"][""] = ["*"]

    return output_selection

def build_optimizer_configuration():
    config = {}
    config["enabled"] = True
    config["runs"] = 200

    return config
