import json
from pathlib import Path
from global_params.types import component_name_T, cfg_object_T
from parser.cfg_object import CFGObject
from parser.cfg_block_list import CFGBlockList
from parser.utils_parser import shorten_name
from typing import Dict, List, Optional, Callable, Tuple
from collections import defaultdict


def store_sfs_json(block_name: str, block: Dict[str, Dict], final_path: Path) -> None:
    """
    Stores all SFS from the list of blocks in the corresponding folder
    """
    short_block_name = shorten_name(block_name)

    file_to_store = final_path.joinpath(short_block_name + ".json")
    with open(file_to_store, 'w') as f:
        json.dump(block, f, indent=4)


class CFG:
    
    def __init__(self, nodeType: str):
        self.nodeType = nodeType
        self.objectCFG: Dict[str, CFGObject] = {}

        # Stores an index for each object
        self.objectCFG2idx: Dict[str, int] = {}

    def add_object(self, name: str, cfg_object: CFGObject) -> None:
        self.objectCFG[name] = cfg_object
        self.objectCFG2idx[name] = len(self.objectCFG2idx)

    def get_object(self, name:str) -> CFGObject:
        return self.objectCFG[name]

    def get_objects(self) -> Dict[str, CFGObject]:
        return self.objectCFG

    def get_object_idx(self, object_name: str) -> int:
        return self.objectCFG2idx[object_name]

    def get_objectCFG2idx(self) -> Dict[str, int]:
        return self.objectCFG2idx

    def get_as_json(self):
        json_cfg = {}
        json_cfg["nodeType"] = self.nodeType

        json_blocks = []
        for block_name, block in self.objectCFG.items():
            json_block = block.get_as_json()
            json_blocks.append(json_block)

        json_obj = {"blocks": json_blocks, "name": self.objectCFG.get("name", "object")}

        json_cfg["object"] = json_obj

        return json_cfg

    def generate_id2block_list(self) -> Dict[cfg_object_T, Dict[component_name_T, CFGBlockList]]:
        """
        Returns the list of all blocks inside the same object, function (excluding subObjects)
        """
        name2block_list = defaultdict(lambda: {})
        for object_id, cfg_object in self.objectCFG.items():
            name2block_list[object_id][object_id] = cfg_object.blocks

            # We also consider the information per function
            for function_name, cfg_function in cfg_object.functions.items():
                name2block_list[object_id][function_name] = cfg_function.blocks

        return name2block_list

    def modify_cfg_block_list(self, f: Callable[[CFGBlockList], CFGBlockList]) -> None:
        """
        Applies a given function to all CFG lists inside the object
        """
        for object_id, cfg_object in self.objectCFG.items():
            modified_block_list = f(cfg_object.blocks)
            cfg_object.blocks = modified_block_list

            # We also consider the information per function
            for function_name, cfg_function in cfg_object.functions.items():
                modified_block_list = f(cfg_function.blocks)
                cfg_function.blocks = modified_block_list

            subobject = cfg_object.get_subobject()

            if subobject is not None:
                subobject.modify_cfg_block_list(f)


    def get_stats(self):
        total_blocks = 0
        total_instructions = 0

        for _cfg_name, cfg_object in self.objectCFG.items():
            blocks, instructions = cfg_object.get_stats()

            total_blocks+= blocks
            total_instructions+= instructions

        return total_blocks, total_instructions


    def dfs(self, object_id):
        return self.objectCFG[object_id].dfs()
    
    def __repr__(self):
        return str(self.get_as_json())
