import json
from typing import Union, Dict, Any
from parser.cfg import CFG
from parser.cfg_object import CFGObject
from parser.cfg_function import CFGFunction
from parser.cfg_block import CFGBlock
from parser.cfg_instruction import CFGInstruction
from parser.utils_parser import check_instruction_validity, check_block_validity

def parse_instruction(ins_json: Dict[str,Any]) -> CFGInstruction:
    in_arg = ins_json.get("in",-1)
    op = ins_json.get("op", -1)
    out_arg = ins_json.get("out", -1)
    check_instruction_validity(in_arg, op, out_arg)

    instruction = CFGInstruction(op,in_arg,out_arg)
    
    builtinargs = ins_json.get("builtinArgs", -1)
    
    if builtinargs != -1:
        instruction.set_builtin_args(builtinargs)

    return instruction


def parse_assignment(assignment: Dict[str, Any], assignment_dict: Dict[str, str]) -> None:
    for in_var, out_var in zip(assignment["in"], assignment["out"]):
        assignment_dict[out_var] = in_var

def parse_block(block_json: Dict[str,Any]) -> CFGBlock:

    block_id = block_json.get("id", -1)
    block_instructions = block_json.get("instructions", -1)
    block_exit = block_json.get("exit", -1)
    block_type = block_json.get("type", "")
    
    check_block_validity(block_id, block_instructions, block_exit, block_type)

    list_cfg_instructions = []
    assignment_dict = dict()
    for instructions in block_instructions:
        if "assignment" in instructions:
            parse_assignment(instructions, assignment_dict)
        else:
            cfg_instruction =parse_instruction(instructions) if block_type != "FunctionReturn" else []
            list_cfg_instructions.append(cfg_instruction)

    block = CFGBlock(block_id,list_cfg_instructions, block_type, assignment_dict)

    if block_type == "FunctionCall":
        block.set_function_call(True)
    
    return block_id, block, block_exit

def parse_function(function_name, function_json):
    
    args = function_json.get("arguments",-1)
    ret_vals = function_json.get("returns",-1)
    entry_point = function_json.get("entry",-1)
    
    cfg_function = CFGFunction(function_name,args,ret_vals,entry_point)

    blocks = function_json.get("blocks",-1)
    for b in blocks:
        block_id, new_block, block_exit = parse_block(b)

        pos = block_id.find("Exit") 
        if pos != -1:
            
            prev_block_id = block_id[:pos]
            prev_block = cfg_function.get_block(prev_block_id)

            prev_block.set_jump_info(new_block.get_jump_type(), block_exit)

            cfg_function.add_exit_point(prev_block_id)
            
        else:
            cfg_function.add_block(new_block)

    return cfg_function
    

def parse_object(object_name, json_object) -> CFGObject:
    blocks_list = json_object.get("blocks",False)

    if not blocks_list:
        raise Exception("[ERROR]: JSON file does not contain blocks")

    cfg_object = CFGObject(object_name)
    
    for bl in blocks_list:
        block_id, new_block, block_exit = parse_block(bl)

        pos = block_id.find("Exit") 
        if pos != -1:
            
            prev_block_id = block_id[:pos]
            prev_block = cfg_object.get_block(prev_block_id)

            prev_block.set_jump_info(new_block.get_jump_type(), block_exit)
            
        else:
            cfg_object.add_block(new_block)

    return cfg_object
    
def parse_CFG(input_file: str):
    json_file = open(input_file, "r")
    json_dict = json.load(json_file)

    nodeType = json_dict.get("type","YulCFG")
    
    cfg = CFG(input_file,nodeType)

    # The contract key corresponds to the key that is neither type nor subobjects
    # For yul blocks, it is "object"
    object_keys = [key for key in json_dict if key not in ["type", "subObjects"]]
    assert len(object_keys) >= 1, "[ERROR]: JSON file does not contain a valid key for the code"
    
    for obj in object_keys:
        json_object = json_dict.get(obj,False)
        cfg_object = parse_object(obj,json_object)
        cfg.add_object(obj,cfg_object)

        json_functions = json_object.get("functions", {})
        for f in json_functions:
            obj_function =parse_function(f,json_functions[f])
            cfg_object.add_function(obj_function)
    # obj_name = obj.get("name")
    # cfg.add_object_name(obj_name)
    



            
    subObjects = json_dict.get("subObjects",-1)
    
    if subObjects == -1:
        raise Exception("[ERROR]: JSON file does not contain key subObjects")

    cfg.add_subobjects(subObjects)

    return cfg