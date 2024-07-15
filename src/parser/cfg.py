import json
from pathlib import Path
from parser.cfg_object import CFGObject
from parser.cfg_block import CFGBlock
from typing import Dict, List


def store_sfs_json(blocks: List[Dict], final_path: Path) -> None:
    """
    Stores all SFS from the list of blocks in the corresponding folder
    """
    for i, block in enumerate(blocks):
        file_to_store = final_path.joinpath(f"block_{i}.json")
        with open(file_to_store, 'w') as f:
            json.dump(block, f, indent=4)


class CFG:
    def __init__(self, nodeType: str):
        self.nodeType = nodeType
        self.objectCFG : Dict[str, CFGObject] = {}
        self.subObjects = {}

    def add_subobjects(self, subobjects):
        self.subObjects = subobjects

    def add_object(self, name:str, cfg_object: CFGObject) -> None:
        self.objectCFG[name] = cfg_object

    def get_object(self, name:str) -> CFGObject:
        return self.objectCFG[name]

    def build_spec_for_objects(self):
        object_dict = {}
        functions_dict = {}
        for o in self.objectCFG:
            specs = self.objectCFG[o].build_spec_for_blocks()
            object_dict[o] = specs

            functions_dict[o] = self.objectCFG[o].build_spec_for_functions()
            
        return object_dict, functions_dict

    def get_as_json(self):
        json_cfg = {}
        json_cfg["nodeType"] = self.nodeType

        json_blocks = []
        for block in self.blocks:
            json_block, json_jump_block = block.get_as_json()
            json_blocks.append(json_block)
            json_blocks.append(json_jump_block)

        json_obj = {}
        json_obj["blocks"] = json_blocks
        json_obj["name"] = self.objectCFG["name"] 
        
        json_cfg["object"] = json_obj
        json_cfg["subObjects"] = self.subObjects

        return json_cfg

    def __str__(self):
        return self.get_as_json()
