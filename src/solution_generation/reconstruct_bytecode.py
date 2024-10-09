"""
Module that contains the methods for reconstructing the bytecode in different formats
"""
from typing import Dict, Any, List, Optional, Union
from global_params.types import SMS_T, ASM_bytecode_T, ASM_contract_T
from parser.cfg import CFG
from parser.cfg_block import CFGBlock

# Solution ids to EVM assembly


def asm_from_op_info(op: str, value: Optional[Union[int, str]] = None,
                     jump_type: Optional[str] = None, source: Optional[int] = -1) -> ASM_bytecode_T:
    """
    JSON asm initialized with default values
    """
    default_asm = {"name": op, "begin": -1, "end": -1, "source": source}

    if value is not None:
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


def asm_for_split_instruction_block(block: CFGBlock) -> List[ASM_bytecode_T]:
    """
    Reconstructs the assembly from a block with a single split instruction
    """
    assert block.get_jump_type() == "split_instruction_block", "[ERROR]: It is not a split_instruction_block"

    instruction_list = block.get_instructions()
    assert len(instruction_list) == 1, "[ERROR]: Split list should contain only one element"
    split_ins = instruction_list[0]
    asm_ins = asm_from_op_info(split_ins.get_op_name().upper())
    asm_subblock = [asm_ins] 

    return asm_subblock


def generate_asm_split_blocks(init_block_id, blocks, asm_dicts):
    asm_block = []

    block = blocks[init_block_id]
    block_id = init_block_id
    
    jump_type = block.get_jump_type()
    while jump_type in ["sub_block","split_instruction_block"]:

        if jump_type == "sub_block":
            asm_subblock = asm_dicts.get(block_id, None)
            assert asm_subblock is not None, "[ERROR]: subblock should contain an asm block"

        elif jump_type == "split_instruction_block":
            asm_subblock = asm_for_split_instruction_block(block)
        else:
            raise Exception("[ERROR]: Jump type can only be subblock or split_intruction")

        asm_block += asm_subblock
        block_id = block.get_falls_to()
        block = blocks[block_id]

        jump_type = block.get_jump_type()
        
    # We translate the last block
    asm_subblock = asm_dicts.get(block_id, None)
    if asm_subblock is None:
        asm_subblock = asm_for_split_instruction_block(block)
        
    asm_block += asm_subblock
    
    return block, asm_block


def traverse_cfg(cfg_object, asm_dicts, tags_dict):
    block_list = cfg_object.get_block_list()
    blocks = block_list.get_blocks_dict()

    init_block = blocks[list(blocks.keys())[0]]

    assert(init_block.get_block_id().find("Block0") != -1)
    
    pending_blocks = [init_block]
    visited = []

    #It is used to know where we have to insert the asm instructions when we have a falls_to
    #It simulates the asm_instructions list with the identifiers of the blocks
    init_pos_dict = []
   
    asm_instructions = []
    
    while pending_blocks != []:
        next_block = pending_blocks.pop()
        
        block_id = next_block.get_block_id()
        visited.append(block_id)

        #If the block has been split we regenerate the whole block together
        #next block contains the last block of the sequence
        if next_block.get_jump_type() in ["sub_block","split_instruction_block"]:
            next_block, asm_block = generate_asm_split_blocks(block_id, blocks, asm_dicts)
        else:
            asm_block = asm_dicts.get(block_id, None)
            
        if block_id in tags_dict:
            tag_asm = asm_from_op_info("tag",str(tags_dict[block_id]))
            jumpdest_asm = asm_from_op_info("JUMPDEST")
            asm_block = [tag_asm,jumpdest_asm]+asm_block
            
        jump_type = next_block.get_jump_type()
        if jump_type == "conditional":
            asm_jumpi = asm_from_op_info("JUMPI")
            asm_instructions+=asm_block
            asm_instructions.append(asm_jumpi)

            init_pos_dict+=[block_id]*(len(asm_block)+1)
            
            jump_to = next_block.get_jump_to()
            falls_to = next_block.get_falls_to()

            if falls_to not in blocks or jump_to not in blocks:
                raise Exception("[ERROR]:...")

            if jump_to not in visited:
                pending_blocks.append(blocks[jump_to])
                
            if falls_to not in visited:
                pending_blocks.append(blocks[falls_to])


        elif jump_type == "unconditional":
            asm_instructions+=asm_block
            asm_jump = asm_from_op_info("JUMP")
            asm_instructions.append(asm_jump)
            init_pos_dict+=[block_id]*(len(asm_block)+1)
            
            jump_to = next_block.get_jump_to()

            if jump_to not in blocks:
                raise Exception("[ERROR]:...")

            if jump_to not in visited:
                pending_blocks.append(blocks[jump_to])
                
        elif jump_type == "sub_block" or jump_type == "split_instruction_block":
            raise Exception("[ERROR]: It should have been considered previously")

        elif jump_type == "falls_to":
            falls_to = next_block.get_falls_to()
            try:
                #It means that the block has been analyzed previously
                pos = init_pos_dict.index(falls_to)
                assert falls_to in visited, \
                    "[ERROR]: Falls_to block should be in visited list when generating asm output"

                asm_instructions = asm_instructions[:pos]+asm_block+asm_instructions[pos:]
                init_pos_dict = init_pos_dict[:pos]+[block_id]*len(asm_block)+init_pos_dict[pos:]
                
            except ValueError:
                asm_instructions += asm_block
                init_pos_dict += [block_id]*len(asm_block)

                pending_blocks.append(falls_to)
                          
        elif jump_type == "terminal":
            asm_instructions += asm_block
            init_pos_dict += [block_id]*len(asm_block)

        else:
            raise Exception("[ERROR]: Unknown jump type when generating asm output")
            
        visited.append(block_id)

    return asm_instructions


# Combine information from the greedy algorithm and the CFG
def asm_from_cfg(cfg: CFG, asm_dicts: Dict[str, List[ASM_bytecode_T]], tags_dict: Dict,
                 filename: str) -> ASM_contract_T:
    objects_cfg = cfg.get_objects()
    subobjects = cfg.get_subobject().get_objects()

    json_object = {}
    for obj_name in objects_cfg.keys():
        obj = objects_cfg[obj_name]

        asm = traverse_cfg(obj, asm_dicts, tags_dict)
        json_asm = {".code": asm}

        json_asm_subobjects = {}
        for idx, deployed_obj in enumerate(subobjects):
            subobj = subobjects[deployed_obj]
            asm_subobj = traverse_cfg(subobj, asm_dicts, tags_dict)

            aux_data = "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
            subobj_asm_code = {".auxdata":aux_data, ".code": asm_subobj}

            #TODO: Comprobar el 0
            json_asm_subobjects[str(idx)]= subobj_asm_code

        json_asm[".data"] = json_asm_subobjects

        json_asm["sourceList"] = [filename]
        
        json_object[filename + ":" +obj_name] = json_asm
        
    return json_object
