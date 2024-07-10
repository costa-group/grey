import json
from pathlib import Path
from parser.cfg_block import CFGBlock
from parser.cfg_function import CFGFunction
from typing import Dict, List

class CFGObject:
    def __init__(self, name):
        self.name = name
        self.blocks : Dict[str, CFGBlock] = {}
        self.functions : Dict[str, CFGFunction] = {}
        
    def add_block(self, block:CFGBlock) -> None:
        block_id = block.get_block_id()

        if block_id in self.blocks:
            if block_id in self.blocks:
                print("WARNING: You are overwritting an existing block")

        self.blocks[block_id] = block

    def add_function(self, function:CFGFunction) -> None:
        function_id = function.get_function_id()

        if function_id in self.functions:
            print("WARNING: You are overwritting an existing function")

        self.functions[function_id] = function

    def get_block(self, block_id):
        return self.blocks[block_id]


    def get_function(self, function_id):
        return self.functions[function_id]

    
    def build_spec_for_blocks(self):
        list_spec = []
        for b in self.blocks:
            block = self.blocks[b]
            spec = block.build_spec()
            list_spec.append(spec)

        return list_spec

    def build_spec_for_functions(self):
        list_spec = []
        for f in self.functions:
            function = self.functions[f]
            spec_list = function.build_spec()
            list_spec.append(spec_list) #It's a list of lists

        return list_spec

    def get_as_json(self):
        json_object = {}

        json_blocks = []
        for block in self.blocks:
            json_block, json_jump_block = block.get_as_json()
            json_blocks.append(json_block)
            json_blocks.append(json_jump_block)

        json_obj = {}
        json_obj["blocks"] = json_blocks

        #TODO: parse functions
        json_obj["functions"] = {}


        return json_obj

    def __str__(self):
        return self.get_as_json()
