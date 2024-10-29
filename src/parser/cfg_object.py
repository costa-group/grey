import json
import logging
from global_params.types import component_name_T
from parser.cfg_block_list import CFGBlockList
from parser.cfg_function import CFGFunction
from typing import Dict, List


class CFGObject:
    def __init__(self, name, blocks):
        self.name = name
        self.blocks: CFGBlockList = blocks
        self.functions: Dict[str, CFGFunction] = {}
        self.block_tag_idx = 0
        
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

    #It marks those blocks in self.blocks that have a function call stored in functions
    def identify_function_calls_in_blocks(self):
        blocks_dict = self.blocks.get_blocks_dict()
        for bl in blocks_dict:
            blocks_dict[bl].process_function_calls(self.functions)

        for f in self.functions:
            f_blocks = self.functions[f].get_blocks_dict()
            for bl in f_blocks:
                f_blocks[bl].process_function_calls(self.functions)
    
    def build_spec_for_functions(self):
        list_spec = {}
        for f in self.functions:
            function = self.functions[f]
            spec_list, self.block_tag_idx = function.build_spec(self.block_tag_idx)
            list_spec[f] = spec_list

        return list_spec

    def get_as_json(self):
        return {"name": self.name}

    def __repr__(self):
        return json.dumps(self.get_as_json())
