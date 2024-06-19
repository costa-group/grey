import json
from typing import Union, Dict, Any
from parser.cfg import CFG
from parser.cfg_block import CFGBlock
from parser.cfg_instruction import CFGInstruction
import parser.utils_parser

def parse_instruction(ins_json: Dict[str,Any]) -> CFGInstruction:
    in_arg = ins_json.get("in",-1)
    op = ins_json.get("op", -1)
    out_arg = ins_json.get("out", -1)
    
    utils.check_instruction_validity(in_arg, op, out_arg)

    instruction = CFGInstruction(op,in_arg,out_arg)
    
    builtinargs = ins_json.get("builtinArgs", -1)
    
    if builtinargs != -1:
        instruction.set_builtin_args(builtinargs)

    return instruction


def parse_block(block_json: Dict[str,Any]) -> CFGBlock:

    block_id = block_json.get("id", -1)
    block_instructions = block_json.get("instructions", -1)
    block_exit = block_json.get("exit", -1)
    block_type = block_json.get("type", -1)
    
    utils.check_block_validity(block_id, block_instructions, block_exit, block_type)

    list_cfg_instructions = []
    for instructions in block_instructions:
        cfg_instruction =parse_instruction(instructions)
        list_cfg_instructions.append(cfg_instruction)

    block = CFGBlock(block_id,list_cfg_instructions, block_type)

    return block_id, block, block_exit


    
def parse_CFG(input_file: str):
    json_dict = json.load(input_file)

    noteType = json_dict.get("nodeType")
    
    cfg = CFG(input_file,nodeType)
    
    obj = json_dict.get("object", False)
    
    if not obj:
        raise Exception ("[ERROR]: JSON file does not contain the key object")

    obj_name = obj.get("name")
    cfg.add_object_name(obj_name)
    
    blocks_list = obj.get("blocks",False)

    if not blocks_list:
        raise Exception("[ERROR]: JSON file does not contain blocks")

    for bl in blocks_list:
        block_id, new_block, block_exit = parse_cfg_block(bl)

        if block_id.find("Exit") != -1:
            prev_block_id = block_id.strip("Exit")[0]
            prev_block = cfg.get_block(prev_block_id)

            prev_block.set_jump_info(new_block.jump_type, block_exit)
            
        else:
            cfg.add_block(bl)


    subObjects = json_dict.get("subObjects",False)

    if not subObjects:
        raise Exception("[ERROR]: JSON file does not contain key subObjects")

    
