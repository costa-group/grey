from typing import TYPE_CHECKING
if TYPE_CHECKING:  # Only imports the below statements during type checking
    from parser.cfg import CFG
import json
import logging
from global_params.types import component_name_T
from parser.cfg_block_list import CFGBlockList
from parser.cfg_function import CFGFunction
from typing import Dict, List, Optional


class CFGObject:
    
    def __init__(self, name, blocks):
        self.name = name
        self.blocks: CFGBlockList = blocks
        self.functions: Dict[str, CFGFunction] = {}
        self.block_tag_idx = 0
        self.subObject: Optional['CFG'] = None

    def set_subobject(self, subobject: 'CFG'):
        self.subObject = subobject

    def get_subobject(self) -> 'CFG':
        return self.subObject

    def add_function(self, function:CFGFunction) -> None:
        function_name = function.get_name()

        if function_name in self.functions:
            print("WARNING: You are overwritting an existing function")
            
        self.functions[function_name] = function
        self.block_tag_idx+=2 #input and output tag of the function
        
    def add_functions(self, functions_list:List[CFGFunction]) -> None:
        for f in functions_list:
            self.add_function(f)
    
    def get_name(self):
        return self.name
            
    def get_block(self, block_id):
        return self.blocks.get_block(block_id)

    def get_block_list(self, name: component_name_T):
        if name == self.name:
            return self.blocks
        function = self.functions.get(name, None)
        if function is not None:
            return function.blocks
        else:
            raise ValueError(f"CFG Object {self.name} does not contain a function named {name}")
    
    def get_function(self, function_id):
        return self.functions[function_id]

    def build_spec_for_blocks(self):
        spec_list, self.block_tag_idx = self.blocks.build_spec(self.block_tag_idx)
        return spec_list

    def identify_function_calls_in_blocks(self):
        """
        Marks the blocks in self.blocks and in the functions that call a function of the object, and restores the
        JSON order of the outputs of these calls (see CFGInstruction.__init__). Must be called exactly once per
        object, right after parsing it: the calls are identified by the names of the functions, so that every
        function gets the same treatment (with or without an underscore in its name, e.g. inline-assembly ones)
        """
        block_lists = [self.blocks] + [self.functions[f] for f in self.functions]
        for block_list in block_lists:
            for block in block_list.get_blocks_dict().values():
                for instruction in block.get_instructions():
                    if instruction.get_op_name() in self.functions:
                        instruction.reverse_out_args()
                block.process_function_calls(self.functions)
    
    def build_spec_for_functions(self):
        list_spec = {}
        for f in self.functions:
            function = self.functions[f]
            spec_list, self.block_tag_idx = function.build_spec(self.block_tag_idx)
            list_spec[f] = spec_list

        return list_spec

    def get_as_json(self):
        return {"name": self.name}


    def get_stats(self):
        total_blocks = 0
        total_instructions = 0

        num_blocks, num_instructions = self.blocks.get_stats()

        total_blocks+=num_blocks
        total_instructions+=num_instructions
        
        for _function_name, function_object in self.functions.items():
            blocks, instructions = function_object.get_stats()

            total_blocks+= blocks
            total_instructions+= instructions


        if self.subObject != None:
            blocks_sub, ins_sub = self.subObject.get_stats()
            total_blocks+= blocks_sub
            total_instructions+=ins_sub
            
        return total_blocks, total_instructions


    def dfs(self):
        return self.blocks.dfs()
    
    
    def __repr__(self):
        return json.dumps(self.get_as_json())
