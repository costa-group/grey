"""
Module that contains the methods for reconstructing the bytecode in different formats
"""
import json
from typing import Dict, Any, List, Optional, Union, Iterable, Tuple
from global_params.types import SMS_T, ASM_bytecode_T, ASM_contract_T, block_id_T, function_name_T
from parser.cfg import CFG
from parser.cfg_object import CFGObject
from parser.cfg_function import CFGFunction
from parser.cfg_block_list import CFGBlockList
from parser.cfg_block import CFGBlock
from pathlib import Path


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
                or associated_instr['disasm'] == "PUSHIMMUTABLE":
            value = hex(int(associated_instr['value'][0]))[2:]
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


def asm_for_split_instruction(block: CFGBlock, tag_dict: Dict[block_id_T, int],
                              function_name2entry: Dict[block_id_T, block_id_T]) -> List[ASM_bytecode_T]:
    """
    Reconstructs the assembly from a block with a single split instruction. If the split instruction is a
    function invocation, then it replaces it by the corresponding JUMP instruction
    """

    assert block.split_instruction is not None, \
        f"[ERROR]: Block {block.block_id} split_instructions has to contain a value in a subblock"

    split_ins = block.split_instruction
    entry_block = function_name2entry.get(split_ins.get_op_name(), None)
    if entry_block is not None:
        # Introduce a JUMP instruction to invoke the function
        asm_ins = asm_from_op_info("JUMP", jump_type="[in]")

    elif split_ins.get_op_name() == "functionReturn":
        # For function returns, we replace them by a JUMP instruction
        asm_ins = asm_from_op_info("JUMP", jump_type="[out]")
    else:
        # Just include the corresponding instruction
        asm_ins = asm_from_op_info(split_ins.get_op_name().upper())

    asm_subblock = [asm_ins]

    return asm_subblock


def generate_asm_split_blocks(init_block_id: block_id_T, blocks: Dict[block_id_T, CFGBlock],
                              tags_dict: Dict[block_id_T, int], asm_dicts: Dict[block_id_T, List[ASM_bytecode_T]],
                              function_name2entry: Dict[function_name_T, block_id_T]) -> Tuple[CFGBlock, List[ASM_bytecode_T]]:
    """
    Joins all the instructions inside all the sub blocks
    """
    asm_block = []

    block = blocks[init_block_id]
    block_id = init_block_id

    jump_type = block.get_jump_type()
    while jump_type in ["sub_block"]:

        if jump_type == "sub_block":
            asm_subblock = asm_dicts.get(block_id, [])
            asm_last = asm_for_split_instruction(block, tags_dict, function_name2entry)

        else:
            raise Exception("[ERROR]: Jump type can only be sub_block")

        asm_block += asm_subblock + asm_last
        block_id = block.get_falls_to()
        block = blocks[block_id]

        jump_type = block.get_jump_type()

    # We translate the last block
    asm_subblock = asm_dicts.get(block_id, [])

    # Split instruction contains both jumps and not handled instructions
    if block.split_instruction is not None:
        asm_last = asm_for_split_instruction(block, tags_dict, function_name2entry)
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
                            asm_dicts: Dict[block_id_T, List[ASM_bytecode_T]],
                            tags_dict: Dict[block_id_T, int]) -> List[ASM_bytecode_T]:
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

    while pending_blocks:
        next_block = pending_blocks.pop()

        block_id = next_block.get_block_id()
        visited.append(block_id)

        # If the block has been split we regenerate the whole block together
        # next block contains the last block of the sequence
        if next_block.get_jump_type() in ["sub_block"]:
            next_block, asm_block = generate_asm_split_blocks(block_id, blocks, tags_dict,
                                                              asm_dicts, function_name2entry)
        else:
            asm_block = asm_dicts.get(block_id, None)

            if next_block.split_instruction is not None:
                asm_last = asm_for_split_instruction(next_block, tags_dict, function_name2entry)
            else:
                # if it is a falls_to or terminal split_instruction is None
                # Otherwise it is jump or jumpi
                asm_last = []

            asm_block += asm_last

        if block_id in tags_dict:
            tag_asm = asm_from_op_info("tag", str(tags_dict[block_id]))
            jumpdest_asm = asm_from_op_info("JUMPDEST")
            asm_block = [tag_asm, jumpdest_asm] + asm_block

        jump_type = next_block.get_jump_type()
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

        elif jump_type == "sub_block":
            raise Exception("[ERROR]: It should have been considered previously")

        elif jump_type == "falls_to":
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

    return asm_instructions


def traverse_cfg(cfg_object: CFGObject, asm_dicts: Dict[block_id_T, List[ASM_bytecode_T]],
                 tags_dict: Dict[block_id_T, int]) -> List[ASM_bytecode_T]:
    """
    Traverses the blocks in the CFG to generate the serialized assembly code
    """
    function_name2entry = generate_function_name2entry(cfg_object.functions.values())
    object_code = traverse_cfg_block_list(cfg_object.blocks, function_name2entry, asm_dicts, tags_dict)

    function_code_list = []
    # TODO: devise better strategies to decide in which order the functions are included in the code
    for function_name, function in cfg_object.functions.items():
        function_code_list.extend(traverse_cfg_block_list(function.blocks, function_name2entry, asm_dicts, tags_dict))
    return object_code + function_code_list


# Combine information from the greedy algorithm and the CFG
def asm_from_cfg(cfg: CFG, asm_dicts: Dict[str, List[ASM_bytecode_T]], tags_dict: Dict,
                 filename: str) -> ASM_contract_T:
    objects_cfg = cfg.get_objects()

    if cfg.get_subobject() is not None:
        subobjects = cfg.get_subobject().get_objects()
    else:
        subobjects = []

    json_object = {}
    for obj_name in objects_cfg.keys():
        obj = objects_cfg[obj_name]

        tags = tags_dict[obj_name]

        asm = traverse_cfg(obj, asm_dicts, tags)
        json_asm = {".code": asm}

        json_asm_subobjects = {}
        for idx, deployed_obj in enumerate(subobjects):
            subobj = subobjects[deployed_obj]
            tags = tags_dict[deployed_obj]
            asm_subobj = traverse_cfg(subobj, asm_dicts, tags)

            aux_data = "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
            subobj_asm_code = {".auxdata": aux_data, ".code": asm_subobj}

            # TODO: Comprobar el 0
            json_asm_subobjects[str(idx)] = subobj_asm_code

        json_asm[".data"] = json_asm_subobjects

        json_asm["sourceList"] = [filename]

        json_object[filename + ":" + obj_name] = json_asm

    return json_object


def store_asm_output(asm_output_dir: Path, json_object: Dict[str, Any], object_name: str):
    file_to_store = asm_output_dir.joinpath(object_name + "_asm.json")
    with open(file_to_store, 'w') as f:
        json.dump(json_object, f, indent=4)
