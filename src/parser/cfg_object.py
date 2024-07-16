import json
import logging
from parser.cfg_block_list import CFGBlockList
from parser.cfg_function import CFGFunction
from typing import Dict, List


class CFGObject:
    def __init__(self, name, blocks):
        self.name = name
        self.blocks: CFGBlockList = CFGBlockList()
        self.functions: Dict[str, CFGFunction] = {}

    def add_function(self, function:CFGFunction) -> None:
        function_name = function.get_name()

        if function_name in self.functions:
            print("WARNING: You are overwritting an existing function")

        self.functions[function_name] = function

    def get_block(self, block_id):
        return self.blocks.get_block(block_id)

    def get_function(self, function_id):
        return self.functions[function_id]

    def build_spec_for_blocks(self):
        return self.blocks.build_spec()

    def build_spec_for_functions(self):
        list_spec = {}
        for f in self.functions:
            function = self.functions[f]
            spec_list = function.build_spec()
            list_spec[f] = spec_list

        return list_spec

    def get_as_json(self):
        pass

    def __str__(self):
        return self.get_as_json()
