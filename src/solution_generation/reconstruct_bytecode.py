"""
Module that contains the methods for reconstructing the bytecode in different formats
"""
from typing import Dict, Any, List, Optional, Union
from global_params.types import SMS_T, ASM_bytecode_T

# Solution ids to EVM assembly


def asm_from_op_info(op: str, value: Optional[Union[int, str]] = None,
                     jump_type: Optional[str] = None, source: Optional[int] = -1) -> ASM_bytecode_T:
    """
    JSON asm initialized with default values
    """
    default_asm = {"name": op, "begin": -1, "end": -1, "source": source}
    if value != None:
        default_asm["value"] = value

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
        else:
            return asm_from_op_info(associated_instr['disasm'],None if 'value' not in associated_instr else associated_instr['value'][0])

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




def traverse_cfg(cfg_object, asm_dicts):
    block_list = cfg_object.get_block_list()
    blocks = block_list.get_blocks_dict()

    init_block = blocks[list(blockskeys())[0]]

    assert(init_block.get_block_id().find("Block0") != -1)
    
    pending_blocks = [init_block]
    asm_instructions = []
    while pending_blocks != []:
        next_block = pendin_blocks.pop(0)
        block_id = next_block.get_block_id()

        asm_block = asm_dicts.get(block_id, None)
        if None:
            #It should be a functions that is not handled
            pass
        else:
            asm_instructions+=asm_block

        if next_block.get_jump_type() == "conditional":
            asm_jumpi = asm_from_op_info("JUMPI")
            asm_instructions.append(asm_jumpi)

            jump_to = next_block.get_jump_to()
            falls_to = next_block.get_falls_to()

            if falls_to not in blocks or jump_to not in blocks:
                raise Exception(["ERROR:..."])
            else:
                pending_blocks.append(blocks[falls_to])
                pending_blocks.append(blocks[jumps_to])
                

# Combine information from the greedy algorithm and the CFG
def asm_from_cfg(cfg, asm_dicts):   
    objects_cfg = cfg.get_objects()
    subObjects = cfg.get_subobject().get_objects()

    json_object = {}
    for obj_name in objects_cfg.keys():
        obj = objects_cfg[obj_name]

        asm = traverse_cfg(obj,asm_dicts)
        
        
    return json_object
