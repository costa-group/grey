import json
from typing import Union, Dict, Any, List, Tuple
from parser.cfg import CFG
from parser.cfg_block_list import CFGBlockList
from parser.cfg_object import CFGObject
from parser.cfg_function import CFGFunction
from parser.cfg_block import CFGBlock
from parser.cfg_instruction import CFGInstruction
from parser.utils_parser import check_instruction_validity, check_block_validity

block_id_T = str


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


def parse_block(block_json: Dict[str,Any]) -> Tuple[block_id_T, CFGBlock, block_id_T]:
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
            cfg_instruction = parse_instruction(instructions) if block_type != "FunctionReturn" else []
            list_cfg_instructions.append(cfg_instruction)

    block = CFGBlock(block_id, list_cfg_instructions, block_type, assignment_dict)

    if block_type == "FunctionCall":
        block.set_function_call(True)
    
    return block_id, block, block_exit


def parser_block_list(blocks: List[Dict[str, Any]]):
    """
    Returns the list of blocks parsed and the ids that correspond to Exit blocks
    """
    block_list = CFGBlockList()
    exit_blocks = []
    for b in blocks:
        block_id, new_block, block_exit = parse_block(b)

        pos = block_id.find("Exit")
        if pos != -1:

            prev_block_id = block_id[:pos]
            prev_block = block_list.get_block(prev_block_id)

            prev_block.set_jump_info(new_block.get_jump_type(), block_exit)
            new_block.add_comes_from(prev_block.block_id)

            exit_blocks.append(prev_block_id)

        else:
            block_list.add_block(new_block)

    return block_list, exit_blocks


def parse_function(function_name, function_json):
    
    args = function_json.get("arguments", -1)
    ret_vals = function_json.get("returns", -1)
    entry_point = function_json.get("entry", -1)

    blocks = function_json.get("blocks", -1)
    cfg_block_list, exit_points = parser_block_list(blocks)

    cfg_function = CFGFunction(function_name, args, ret_vals, entry_point, cfg_block_list)
    cfg_function.exits = exit_points
    return cfg_function
    

def parse_object(object_name, json_object) -> CFGObject:
    blocks_list = json_object.get("blocks",False)

    if not blocks_list:
        raise Exception("[ERROR]: JSON file does not contain blocks")

    cfg_block_list, _ = parser_block_list(blocks_list)
    cfg_object = CFGObject(object_name, cfg_block_list)

    return cfg_object


def parser_CFG_from_JSON(json_dict: Dict):
    nodeType = json_dict.get("type","YulCFG")
    
    cfg = CFG(nodeType)

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
            obj_function = parse_function(f, json_functions[f])
            cfg_object.add_function(obj_function)
    # obj_name = obj.get("name")
    # cfg.add_object_name(obj_name)

    subObjects = json_dict.get("subObjects", -1)
    
    if subObjects == -1:
        raise Exception("[ERROR]: JSON file does not contain key subObjects")

    cfg.add_subobjects(subObjects)

    return cfg


def parse_CFG(input_file: str):
    with open(input_file, "r") as f:
        json_dict = json.load(f)
    return parser_CFG_from_JSON(json_dict)
