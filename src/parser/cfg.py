import json
from pathlib import Path
from parser.cfg_object import CFGObject
from parser.cfg_block_list import CFGBlockList
from typing import Dict, List, Optional, Callable


def store_sfs_json(block_name: str, block: Dict[str, Dict], final_path: Path) -> None:
    """
    Stores all SFS from the list of blocks in the corresponding folder
    """
    file_to_store = final_path.joinpath(block_name + ".json")
    with open(file_to_store, 'w') as f:
        json.dump(block, f, indent=4)


class CFG:
    def __init__(self, nodeType: str):
        self.nodeType = nodeType
        self.objectCFG: Dict[str, CFGObject] = {}
        self.subObjects: Optional[CFG] = None

        # Points each object/function/subobject name to its block list
        self.block_list: Dict[str, CFGBlockList] = {}

    def add_object(self, name: str, cfg_object: CFGObject) -> None:
        self.objectCFG[name] = cfg_object

        # Once an object is stored, we keep a dictionary with all the blocklists and the name
        # of the corresponding structure
        self.block_list[name] = cfg_object.blocks
        for function_name, cfg_function in cfg_object.functions.items():
            self.block_list[function_name] = cfg_function.blocks

    def get_object(self, name:str) -> CFGObject:
        return self.objectCFG[name]

    def get_objects(self) -> Dict[str, CFGObject]:
        return self.objectCFG
    
    def set_subobject(self, subobject: 'CFG'):
        self.subObjects = subobject

        # Add all the definitions in the subobject
        self.block_list.update(subobject.block_list)

    def get_subobject(self) -> 'CFG':
        return self.subObjects

    def build_spec_for_objects(self):
        object_dict = {}
        functions_dict = {}
        for o in self.objectCFG:
            specs = self.objectCFG[o].build_spec_for_blocks()
            object_dict[o] = specs

            functions_dict[o] = self.objectCFG[o].build_spec_for_functions()

        if self.subObjects is not None:
            subobject_dict, subfunction_dict = self.subObjects.build_spec_for_objects()
            object_dict.update(subobject_dict)
            functions_dict.update(subfunction_dict)

        return object_dict, functions_dict

    def get_as_json(self):
        json_cfg = {}
        json_cfg["nodeType"] = self.nodeType

        json_blocks = []
        for block_name, block in self.objectCFG.items():
            json_block = block.get_as_json()
            json_blocks.append(json_block)

        json_obj = {"blocks": json_blocks, "name": self.objectCFG.get("name", "object")}

        json_cfg["object"] = json_obj
        json_cfg["subObjects"] = self.subObjects

        return json_cfg

    def cfg_block_list(self) -> List[CFGBlockList]:
        """
        Returns the list of all blocks inside the same object, function and subobjects
        """
        block_list = []
        for object_id, cfg_object in self.objectCFG.items():
            block_list.append(cfg_object.blocks)

            # We also consider the information per function
            for function_name, cfg_function in cfg_object.functions.items():
                block_list.append(cfg_function.blocks)

            subobject = self.get_subobject()

            if subobject is not None:
                block_list.extend(subobject.cfg_block_list())

        return block_list

    def modify_cfg_block_list(self, f: Callable[[CFGBlockList], CFGBlockList]) -> None:
        """
        Applies a given function to all CFG lists inside the object
        """
        for object_id, cfg_object in self.objectCFG.items():
            modified_block_list = f(cfg_object.blocks)
            cfg_object.blocks = modified_block_list
            self.block_list[object_id] = modified_block_list

            # We also consider the information per function
            for function_name, cfg_function in cfg_object.functions.items():
                modified_block_list = f(cfg_function.blocks)
                cfg_function.blocks = modified_block_list
                self.block_list[function_name] = modified_block_list

            subobject = self.get_subobject()

            if subobject is not None:
                subobject.modify_cfg_block_list(f)

                # Modify the block list with the information from the subobject
                self.block_list.update(subobject.block_list)

    def __repr__(self):
        return str(self.get_as_json())
