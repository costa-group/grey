import collections
import json
from typing import Union, Dict, Any, List, Tuple, Set
from global_params.types import Yul_CFG_T, block_id_T, component_name_T
from parser.cfg import CFG
from parser.cfg_block_list import CFGBlockList
from parser.cfg_object import CFGObject
from parser.cfg_function import CFGFunction
from parser.cfg_block import CFGBlock
from parser.cfg_instruction import CFGInstruction
from parser.utils_parser import check_instruction_validity, check_block_validity, check_assignment_validity, split_json


def generate_block_name(object_name: component_name_T, block_id: block_id_T) -> block_id_T:
    """
    Block name used to identify the blocks
    """
    return '_'.join([object_name, block_id])


def parse_instruction(ins_json: Dict[str, Any], assgiment_dict: Dict[str,str]) -> CFGInstruction:
    in_arg = ins_json.get("in",-1)
    op = ins_json.get("op", -1)
    out_arg = ins_json.get("out", -1)

    check_instruction_validity(in_arg, op, out_arg)

    if op == "LiteralAssigment":
        assigment_dict[out_arg[0]] = in_arg[0]
    
    instruction = CFGInstruction(op,in_arg,out_arg)
    
    literalargs = ins_json.get("literalArgs", -1)
    
    if literalargs != -1:
        instruction.set_literal_args(literalargs)

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


def parse_block(object_name: str, block_json: Dict[str,Any], built_in_op: bool,
                objects_keys: Dict[str, int], assigment_dict: Dict[str,str]) -> Tuple[block_id_T, CFGBlock, Dict]:
    block_id = block_json.get("id", -1)
    block_instructions = block_json.get("instructions", -1)
    block_exit = block_json.get("exit", -1)
    block_type = block_json.get("type", "")
    entries = [generate_block_name(object_name, target) for target in block_json.get("entries", [])]

    # Modify the block exit targets with the new information
    block_exit["targets"] = [generate_block_name(object_name, target) for target in block_exit.get("targets", [])]
    check_block_validity(block_id, block_instructions, block_exit, block_type)
    
    list_cfg_instructions = []
    for instruction in block_instructions:
        cfg_instruction = parse_instruction(instruction, assigment_dict) if block_type != "FunctionReturn" else []

        # if not built_in_op and cfg_instruction != []:
        #     cfg_instruction.translate_opcode(objects_keys)

        list_cfg_instructions.append(cfg_instruction)

    block_liveness = block_json.get("liveness", {})
    block_identifier = generate_block_name(object_name, block_id)
    block = CFGBlock(block_identifier, list_cfg_instructions, block_type, dict())
    block.set_liveness(block_liveness)
    block.set_jump_info(block_exit)
    block.entries = entries

    block.check_validity_arguments()
    
    if block_type == "FunctionCall":
        block.set_function_call(True)

    # block._process_dependences(block._instructions)
        
    return block_identifier, block, block_exit


def update_comes_from(block_list: CFGBlockList, comes_from: Dict[str, List[str]]) -> None:
    """
    Update comes_from fields in the blocks from the block list using the information from the dictionary
    """
    for block_id in comes_from:
        for predecessor in comes_from[block_id]:
            # TODO: Ask why last block references itself
            if block_id != predecessor:
                block_list.get_block(block_id).add_comes_from(predecessor)


def parser_block_list(object_name: str, blocks: List[Dict[str, Any]], built_in_op: bool, objects_keys: Dict[str, int]):
    """
    Returns the list of blocks parsed and the ids that correspond to Exit blocks
    """
    block_list = CFGBlockList(object_name)
    exit_blocks = []
    comes_from = collections.defaultdict(lambda: [])
    assigment_dict = {}
    
    for b in blocks:
        block_id, new_block, block_exit = parse_block(object_name, b, built_in_op, objects_keys,assigment_dict)

        # Annotate comes from
        for succ_block in block_exit["targets"]:
            comes_from[succ_block].append(block_id)

        if new_block.get_jump_type() == "terminal":
            exit_blocks.append(block_id)

        block_list.add_block(new_block)

    if not built_in_op:
        block_list.translate_opcodes(objects_keys)
        #     cfg_instruction.translate_opcode(objects_keys)


    
    # We need to update some fields in the blocks using the previously gathered information
    update_comes_from(block_list, comes_from)

    block_list.set_assigment(assigment_dict)
    
    return block_list, exit_blocks


def parse_function(function_name: str, function_json: Dict[str,Any], built_in_op: bool, objects_keys: Dict[str, int]):
    args = list(reversed(function_json.get("arguments", [])))
    ret_vals = function_json.get("returns", [])
    entry_point = function_json.get("entry", "")

    blocks = function_json.get("blocks", [])
    cfg_block_list, exit_points = parser_block_list(function_name, blocks, built_in_op, objects_keys)

    cfg_function = CFGFunction(function_name, args, ret_vals, generate_block_name(function_name, entry_point),
                               cfg_block_list)
    cfg_function.exits = exit_points
    return cfg_function
    

def parse_object(object_name: str, json_object: Dict[str,Any], built_in_op: bool, objects_keys: Dict[str, int]) -> CFGObject:
    blocks_list = json_object.get("blocks", None)

    if blocks_list is None:
        raise Exception("[ERROR]: JSON file does not contain blocks")

    cfg_block_list, _ = parser_block_list(object_name, blocks_list, built_in_op, objects_keys)
    cfg_object = CFGObject(object_name, cfg_block_list)
    
    return cfg_object
    
    
def parser_CFG_from_JSON(json_dict: Dict, built_in_op: bool):
    nodeType = json_dict.get("type","YulCFG")
    
    cfg = CFG(nodeType)

    # The contract key corresponds to the key that is neither type nor subobjects
    # For yul blocks, it is "object"
    object_keys = [key for key in json_dict if key not in ["type", "subObjects"]]

    assert len(object_keys) >= 1, "[ERROR]: JSON file does not contain a valid key for the code"

    for obj in object_keys:
        json_object = json_dict.get(obj, False)
        json_functions = json_object.get("functions", {})

        # First, we parse the subObjects in order to generate the corresponding keys dict
        subObjects = json_object.get("subObjects", {})

        key_dict = dict()

        if subObjects != {}:
            sub_object = parser_CFG_from_JSON(subObjects, built_in_op)
            key_dict = sub_object.get_objectCFG2idx()

        cfg_object = parse_object(obj, json_object, built_in_op, key_dict)

        if subObjects != {}:
            cfg_object.set_subobject(sub_object)

        for f in json_functions:
            obj_function = parse_function(f, json_functions[f], built_in_op, key_dict)
            cfg_object.add_function(obj_function)

        # Important: add the object already initialized with the functions, so that we can construct
        # link the corresponding block lists in the CFG
        cfg.add_object(obj, cfg_object)

        cfg_object.identify_function_calls_in_blocks()

    # obj_name = obj.get("name")
    # cfg.add_object_name(obj_name)

    return cfg


def parse_CFG_from_json_dict(json_dict: Dict[str, Yul_CFG_T], built_in_op=False):
    """
    Given a dictionary of Yul CFG jsons, generates a CFG for each JSON
    """
    cfg_dicts = {}
    for cfg_name, json_dict in json_dict.items():
        print("CFG NAME: "+cfg_name)
        #print(json_dict)
        cfg = parser_CFG_from_JSON(json_dict, built_in_op)
        cfg_dicts[cfg_name] = cfg
    return cfg_dicts
