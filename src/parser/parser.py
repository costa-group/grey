import collections
import json
from typing import Union, Dict, Any, List, Tuple, Set
from global_params.types import Yul_CFG_T
from parser.cfg import CFG
from parser.cfg_block_list import CFGBlockList
from parser.cfg_object import CFGObject
from parser.cfg_function import CFGFunction
from parser.cfg_block import CFGBlock
from parser.cfg_instruction import CFGInstruction
from parser.utils_parser import check_instruction_validity, check_block_validity, check_assignment_validity, split_json

block_id_T = str


def generate_block_name(object_name: str, block_id: block_id_T) -> block_id_T:
    """
    Block name used to identify the blocks
    """
    return '_'.join([object_name, block_id])


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


def parse_assignment(assignment: Dict[str, Any], assignment_dict: Dict[str, str]) -> CFGInstruction:
    """
    Assignments are handled differently than other instructions, as they have no op field and (theoretically)
    multiple assignments can be made at the same time. An instruction is generated per assignment
    """
    in_args = assignment.get("in", -1)
    assignment_args = assignment.get("assignment", -1)
    out_args = assignment.get("out", -1)

    check_assignment_validity(in_args, assignment_args, out_args)

    # Assignments are combined into a single instruction, maintaining the original format
    instruction = CFGInstruction("assignments", in_args, out_args)

    # Extend the assignment dict with the corresponding information
    for in_var, out_var in zip(in_args, out_args):
        assignment_dict[out_var] = in_var

    return instruction


def process_block_entry(block_json: Dict[str, Any], phi_instr: Dict[str, Any]) -> Dict[str, Tuple[str, str]]:
    """
    Given a block and a Phi instruction, generates a dict that links each of the predecessor blocks and the
    corresponding value
    """
    # If there is a PhiFunction, there is an entry field
    block_entry = block_json["entries"]
    # Stores the entries and the corresponding values in a dict, as it can affect other blocks

    block_entry_values = phi_instr["in"]

    # Assumption: phi instructions just have one value
    output_value = phi_instr["out"][0]

    return {entry: (input_value, output_value) for entry, input_value in zip(block_entry, block_entry_values)}


def parse_block(object_name: str, block_json: Dict[str,Any], function_calls: Set[str],
                built_in_op: bool, objects_keys: List[str]) -> Tuple[block_id_T, CFGBlock, Dict, Dict[str, Tuple[str, str]]]:
    block_id = block_json.get("id", -1)
    block_instructions = block_json.get("instructions", -1)
    block_exit = block_json.get("exit", -1)
    block_type = block_json.get("type", "")

    # Modify the block exit targets with the new information
    block_exit["targets"] = [generate_block_name(object_name, target) for target in block_exit.get("targets", [])]
    check_block_validity(block_id, block_instructions, block_exit, block_type)
    
    list_cfg_instructions = []
    assignment_dict = dict()
    entry_dict = dict()
    for instruction in block_instructions:
        if "assignment" in instruction:
            list_cfg_instructions.append(parse_assignment(instruction, assignment_dict))
        # We handle Phi functions separately
        elif instruction["op"] == "PhiFunction":
            # Beware: we need to keep the same name we are using to identify the blocks
            entry_dict.update((generate_block_name(object_name, entry), values)
                              for entry, values in process_block_entry(block_json, instruction).items())

        else:
            cfg_instruction = parse_instruction(instruction) if block_type != "FunctionReturn" else []

            if not built_in_op and cfg_instruction != []:
                cfg_instruction.translate_opcode(objects_keys)

            list_cfg_instructions.append(cfg_instruction)

    block_identifier = generate_block_name(object_name, block_id)
    block = CFGBlock(block_identifier, list_cfg_instructions, block_type, assignment_dict)
    block.set_jump_info(block_exit)
    block.process_function_calls(function_calls)

    block.check_validity_arguments()
    
    if block_type == "FunctionCall":
        block.set_function_call(True)

    # block._process_dependences(block._instructions)
        
    return block_identifier, block, block_exit, entry_dict


def update_comes_from(block_list: CFGBlockList, comes_from: Dict[str, List[str]]) -> None:
    """
    Update comes_from fields in the blocks from the block list using the information from the dictionary
    """
    for block_id in comes_from:
        for predecessor in comes_from[block_id]:
            # TODO: Ask why last block references itself
            if block_id != predecessor:
                block_list.get_block(block_id).add_comes_from(predecessor)


def update_assignments_from_phi_functions(block_list: CFGBlockList, phi_function_dict: Dict[str, Tuple[str, str]]) -> None:
    """
    Given the list of blocks and the phi functions that appear in any of those blocks, introduces the values
    that are constants from the phi function in the corresponding block as part of the assignments
    """
    for block_id, (input_value, output_value) in phi_function_dict.items():
        block = block_list.get_block(block_id)

        # We update the assignments of constants
        if input_value.startswith("0x"):
            block.assignment_dict[output_value] = input_value


def parser_block_list(object_name: str, blocks: List[Dict[str, Any]], function_calls: Set[str], built_in_op : bool, objects_keys : List[str]):
    """
    Returns the list of blocks parsed and the ids that correspond to Exit blocks
    """
    block_list = CFGBlockList(object_name)
    exit_blocks = []
    comes_from = collections.defaultdict(lambda: [])
    for b in blocks:
        block_id, new_block, block_exit, block_entries = parse_block(object_name, b, function_calls, built_in_op, objects_keys)

        # Annotate comes from
        for succ_block in block_exit["targets"]:
            comes_from[succ_block].append(block_id)

        if new_block.get_jump_type() == "terminal":
            exit_blocks.append(block_id)

        block_list.add_block(new_block)
        block_list.entry_dict.update(block_entries)

    # We need to update some fields in the blocks using the previously gathered information
    update_comes_from(block_list, comes_from)
    update_assignments_from_phi_functions(block_list, block_list.entry_dict)

    return block_list, exit_blocks


def parse_function(function_name: str, function_json: Dict[str,Any], function_calls: Set[str], built_in_op: bool, objects_keys: List[str]):
    
    args = function_json.get("arguments", -1)
    ret_vals = function_json.get("returns", -1)
    entry_point = function_json.get("entry", -1)

    blocks = function_json.get("blocks", -1)
    cfg_block_list, exit_points = parser_block_list(function_name, blocks, function_calls, built_in_op, objects_keys)

    cfg_function = CFGFunction(function_name, args, ret_vals, generate_block_name(function_name, entry_point),
                               cfg_block_list)
    cfg_function.exits = exit_points
    return cfg_function
    

def parse_object(object_name: str, json_object: Dict[str,Any], function_calls: Set[str], built_in_op: bool, objects_keys: List[str]) -> CFGObject:
    blocks_list = json_object.get("blocks", None)

    if blocks_list is None:
        raise Exception("[ERROR]: JSON file does not contain blocks")

    cfg_block_list, _ = parser_block_list(object_name, blocks_list, function_calls, built_in_op, objects_keys)
    cfg_object = CFGObject(object_name, cfg_block_list)

    return cfg_object
    
    
def parser_CFG_from_JSON(json_dict: Dict, built_in_op: bool):
    nodeType = json_dict.get("type","YulCFG")
    
    cfg = CFG(nodeType)

    # The contract key corresponds to the key that is neither type nor subobjects
    # For yul blocks, it is "object"
    object_keys = [key for key in json_dict if key not in ["type", "subObjects"]]

    subobjects_keys = [key for key in json_dict.get("subObjects") if key not in ["type", "subObjects"]] if json_dict.get("subObjects",{}) != {} else []

    obj_json_keys = object_keys+subobjects_keys
    
    assert len(object_keys) >= 1, "[ERROR]: JSON file does not contain a valid key for the code"
    
    for obj in object_keys:
        json_object = json_dict.get(obj,False)
        json_functions = json_object.get("functions", {})

        cfg_object = parse_object(obj,json_object, json_functions, built_in_op, obj_json_keys)

        for f in json_functions:
            obj_function = parse_function(f, json_functions[f], json_functions, built_in_op, obj_json_keys)
            cfg_object.add_function(obj_function)

        # Important: add the object already initialized with the functions, so that we can construct
        # link the corresponding block lists in the CFG
        cfg.add_object(obj, cfg_object)

        cfg_object.identify_function_calls_in_blocks()
    # obj_name = obj.get("name")
    # cfg.add_object_name(obj_name)

    subObjects = json_dict.get("subObjects", -1)
    
    if subObjects == -1:
        raise Exception("[ERROR]: JSON file does not contain key subObjects")

    if subObjects != {}:
        sub = parser_CFG_from_JSON(subObjects, built_in_op)
        cfg.set_subobject(sub)
        
    return cfg


def parse_CFG_from_json_dict(json_dict: Dict[str, Yul_CFG_T], built_in_op=False):
    """
    Given a dictionary of Yul CFG jsons, generates a CFG for each JSON
    """
    cfg_dicts = {}
    for cfg_name, json_dict in json_dict.items():
        cfg = parser_CFG_from_JSON(json_dict, built_in_op)
        cfg_dicts[cfg_name] = cfg

    return cfg_dicts
