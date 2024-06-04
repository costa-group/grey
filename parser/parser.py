import json
from typing import Union, Dict, Any
from parser.cfg import CFG
from parser.cfg_block import CFGBlock

def parse_block(block_json: Dict[str,Any]) -> CFGBlock:

    block_id = block_json.get("Id", -1)
    block_instructions = block_json.get("Instructions", -1)
    block_exit = block_json.get("Exit", -1)
    block_type = block_json.get("type", -1)
    
    check_block_validity(block_id, block_instructions, block_exit, block_type)
    



def check_block_validity(block_id, block_instructions, block_exit, block_type):
    if block_id == -1:
        raise Exception("[ERROR]: Input block does not contain an identifier")

    if block_instructions == -1:
        raise Exception("[ERROR]: Input block does not contain instructions")

    if block_exit == -1:
        raise Exception("[ERROR]: Input block does not contain an exit")

    if block_type == -1:
        raise Exception("[ERROR]: Input block does not contain an identifier")
    
def parse_CFG(input_file: src):
    json_dict = json.load(input_file)

    blocks_list = json_dict.get("blocks",False)

    if not blocks_list:
        raise Exception("ERROR: JSON file does not contain blocks")

    cfg = CFG(input_file)
                        
    for bl in blocks_list:
        new_block = parse_cfg_block(bl)
        cfg.add_block(bl)
